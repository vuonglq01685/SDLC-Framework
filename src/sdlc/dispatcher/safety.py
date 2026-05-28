"""Destructive tool-call safety helpers (Story 2B.6 AC3)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Final

from sdlc.specialists.frontmatter import Specialist

# NFR-SEC-3 destructive-operation re-confirmation tokens (Story 2B.5 AC3).
DESTRUCTIVE_FILE_DELETE_TOKEN: Final[str] = "RECONFIRM_FILE_DELETE"
DESTRUCTIVE_FORCE_PUSH_TOKEN: Final[str] = "RECONFIRM_FORCE_PUSH"
DESTRUCTIVE_DROP_DATABASE_TOKEN: Final[str] = "RECONFIRM_DROP_DATABASE"
_DESTRUCTIVE_OPS_BLOCK: Final[str] = (
    "<DESTRUCTIVE_OPS>\n"
    "Before proposing or executing a destructive operation, obtain explicit "
    "human re-confirmation and cite the matching token:\n"
    f"- file delete: {DESTRUCTIVE_FILE_DELETE_TOKEN}\n"
    f"- force-push: {DESTRUCTIVE_FORCE_PUSH_TOKEN}\n"
    f"- drop database: {DESTRUCTIVE_DROP_DATABASE_TOKEN}\n"
    "</DESTRUCTIVE_OPS>"
)


def _should_inject_destructive_block(specialist: Specialist) -> bool:
    """True when specialist writes outside _bmad-output/ (CR2B5-W2 scoping)."""
    g = specialist.frontmatter.write_globs
    return bool(g) and any(not x.startswith("_bmad-output/") for x in g)


def _build_destructive_ops_block(nonce: str | None) -> str:
    """Destructive-ops prompt block; tokens qualified with nonce when provided (CR2B5-W1)."""
    if nonce is None:
        return _DESTRUCTIVE_OPS_BLOCK
    return (
        "<DESTRUCTIVE_OPS>\n"
        "Before proposing or executing a destructive operation, obtain explicit "
        "human re-confirmation and cite the matching token:\n"
        f"- file delete: {DESTRUCTIVE_FILE_DELETE_TOKEN}_{nonce}\n"
        f"- force-push: {DESTRUCTIVE_FORCE_PUSH_TOKEN}_{nonce}\n"
        f"- drop database: {DESTRUCTIVE_DROP_DATABASE_TOKEN}_{nonce}\n"
        f"Session nonce: {nonce}\n"
        "</DESTRUCTIVE_OPS>"
    )


_EXCERPT_LEN: Final[int] = 200
_DESTRUCTIVE_TOOL_PATTERNS: Final[dict[str, re.Pattern[str]]] = {
    "file_delete": re.compile(r"\brm\s+(-rf|-fr)\b"),
    "force_push": re.compile(r"\bgit\s+push\s+(-f|--force|--force-with-lease)\b"),
    "drop_database": re.compile(r"\bDROP\s+(DATABASE|TABLE|SCHEMA)\b", re.IGNORECASE),
}


def tool_call_excerpt(tool_call: Mapping[str, object]) -> str:
    cmd = tool_call.get("command")
    raw = cmd if isinstance(cmd, str) else str(tool_call)
    return raw[:_EXCERPT_LEN]


def is_destructive(tool_call: Mapping[str, object]) -> tuple[bool, str | None]:
    name = tool_call.get("name")
    if name != "Bash":
        return (False, None)
    command = tool_call.get("command")
    if not isinstance(command, str):
        return (False, None)
    for category, pattern in _DESTRUCTIVE_TOOL_PATTERNS.items():
        if pattern.search(command):
            return (True, category)
    return (False, None)


def prompt_for_reconfirmation(nonce: str, category: str, tool_call_excerpt: str) -> bool:
    response = input(
        f"Destructive operation detected ({category}): {tool_call_excerpt}\n"
        f"Type nonce to proceed: {nonce}\n> "
    )
    return response == nonce
