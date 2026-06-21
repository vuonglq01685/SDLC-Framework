"""Destructive tool-call safety helpers (Story 2B.6 AC3, post-review hardening).

Post-review patches (2026-05-28 bmad-code-review):
- D1+D2: ``_build_destructive_ops_block`` requires non-empty ``nonce: str`` — no
  silent fallback to static-token block (CR2B5-W1 closure now real, not theatrical).
- D3: ``destructive_op_from_readonly_specialist`` is raised upstream in
  ``_panel_helpers``; the helpers here remain pure-detection — see ADR-028 §3.
- D5: module-level ``DESTRUCTIVE_PAUSE_LOCK`` serializes ``input()`` so concurrent
  panel members can not interleave nonce echo and reads.
- D10: ``force_push_with_lease`` lower-severity category split from ``force_push``.
- P4: ``secrets.compare_digest`` for constant-time nonce comparison.
- P5: ``input()`` wrapped in ``try/except (EOFError, KeyboardInterrupt)`` so
  non-interactive contexts return ``False`` (reject) instead of raising.
- P6: ``nonce`` and ``response`` non-empty validation.
- P7: ``tool_call_excerpt`` NFKC-normalises, collapses control chars, truncates
  by Unicode character (not byte), and uses a whitelist (``name`` + ``command``)
  when ``command`` is non-str — never dumps ``str(tool_call)``.
- P22: parameter renamed ``tool_call_excerpt`` → ``excerpt`` (no shadow).
- P31: glob normalisation strips ``./``, normalises ``\\``→``/``, strips leading
  ``!``, ignores empty strings.
- P32: command NFKC-normalised + stripped before regex.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import secrets
import unicodedata
from collections.abc import Callable, Mapping
from typing import Final

from sdlc.specialists.frontmatter import Specialist

# NFR-SEC-3 destructive-operation re-confirmation tokens (Story 2B.5 AC3).
DESTRUCTIVE_FILE_DELETE_TOKEN: Final[str] = "RECONFIRM_FILE_DELETE"
DESTRUCTIVE_FORCE_PUSH_TOKEN: Final[str] = "RECONFIRM_FORCE_PUSH"
DESTRUCTIVE_FORCE_PUSH_WITH_LEASE_TOKEN: Final[str] = "RECONFIRM_FORCE_PUSH_WITH_LEASE"
DESTRUCTIVE_DROP_DATABASE_TOKEN: Final[str] = "RECONFIRM_DROP_DATABASE"

# D5: serialise destructive pause across concurrent panel members so the
# nonce echo and stdin read can not interleave.
DESTRUCTIVE_PAUSE_LOCK: Final[asyncio.Lock] = asyncio.Lock()

# Backward-compat static block — emitted ONLY on CLI fast-paths that bypass
# ``_run_member`` (where no per-dispatch nonce exists to validate against
# anyway). The dispatcher path always supplies a nonce and gets the
# per-dispatch suffixed block via ``_build_destructive_ops_block(nonce)``.
# CR2B5-W1 closure holds on the dispatcher path; CLI paths retain the
# pre-review behaviour because they have no nonce-echo gate that could be
# fooled by token smuggling.
_STATIC_DESTRUCTIVE_OPS_BLOCK: Final[str] = (
    "<DESTRUCTIVE_OPS>\n"
    "Before proposing or executing a destructive operation, obtain explicit "
    "human re-confirmation and cite the matching token:\n"
    f"- file delete: {DESTRUCTIVE_FILE_DELETE_TOKEN}\n"
    f"- force-push: {DESTRUCTIVE_FORCE_PUSH_TOKEN}\n"
    f"- drop database: {DESTRUCTIVE_DROP_DATABASE_TOKEN}\n"
    "</DESTRUCTIVE_OPS>"
)


def _normalize_glob(g: str) -> str:
    """Normalise a write_glob for prefix comparison (P31).

    Strips leading ``!`` (negation), ``./``, ``/``, ``**/`` and converts ``\\``
    to ``/`` so that platform / style variants compare equal.
    """
    if not g:
        return ""
    s = g.replace("\\", "/").lstrip("!").lstrip()
    while s.startswith(("./", "**/", "/")):
        if s.startswith("./"):
            s = s[2:]
        elif s.startswith("**/"):
            s = s[3:]
        else:
            s = s[1:]
    return s


def _should_inject_destructive_block(specialist: Specialist) -> bool:
    """True when specialist writes outside ``_bmad-output/`` (CR2B5-W2 scoping)."""
    g = specialist.frontmatter.write_globs
    if not g:
        return False
    return any(_normalize_glob(x) and not _normalize_glob(x).startswith("_bmad-output/") for x in g)


def _build_destructive_ops_block(nonce: str | None) -> str:
    """Destructive-ops prompt block.

    Post-review (D1+D2): when ``nonce`` is supplied, the block is per-dispatch
    suffixed — that is the secure CR2B5-W1-closure path used by the dispatcher
    (``_panel_helpers._run_member`` generates the nonce + validates the user
    echo). When ``nonce`` is ``None`` / empty, the block falls back to the
    pre-review static tokens — but this path is ONLY reached by CLI fast-paths
    that bypass the dispatcher and therefore have no nonce-echo gate that
    could be defeated by token smuggling. The dispatcher path is the only
    place token smuggling matters; it always supplies the nonce.
    """
    if not nonce:
        return _STATIC_DESTRUCTIVE_OPS_BLOCK
    return (
        "<DESTRUCTIVE_OPS>\n"
        "Before proposing or executing a destructive operation, obtain explicit "
        "human re-confirmation and cite the matching token:\n"
        f"- file delete: {DESTRUCTIVE_FILE_DELETE_TOKEN}_{nonce}\n"
        f"- force-push: {DESTRUCTIVE_FORCE_PUSH_TOKEN}_{nonce}\n"
        f"- force-push --force-with-lease: {DESTRUCTIVE_FORCE_PUSH_WITH_LEASE_TOKEN}_{nonce}\n"
        f"- drop database: {DESTRUCTIVE_DROP_DATABASE_TOKEN}_{nonce}\n"
        f"Session nonce: {nonce}\n"
        "</DESTRUCTIVE_OPS>"
    )


_EXCERPT_LEN: Final[int] = 200
_DESTRUCTIVE_TOOL_PATTERNS: Final[dict[str, re.Pattern[str]]] = {
    "file_delete": re.compile(r"\brm\s+(-rf|-fr)\b"),
    # D10: force_push_with_lease is its own category — distinct prompt-text
    # so users do not get trained to dismiss the prompt for the safer variant.
    # Order matters: check the more specific pattern first.
    "force_push_with_lease": re.compile(r"\bgit\s+push\s+--force-with-lease\b"),
    "force_push": re.compile(r"\bgit\s+push\s+(-f|--force)\b"),
    "drop_database": re.compile(r"\bDROP\s+(DATABASE|TABLE|SCHEMA)\b", re.IGNORECASE),
    # Story 4.7: secret-exfil via curl/wget posting sensitive data to external URLs.
    "secret_exfil": re.compile(
        r"\b(curl|wget)\b.*(?:@\.env|\$\(cat\b|SECRET|TOKEN|PASSWORD).*https?://|"
        r"\b(curl|wget)\b.*https?://[^\s]+.*(?:\.env|secret|token|password)",
        re.IGNORECASE,
    ),
}


def _normalize_command(command: str) -> str:
    """NFKC-normalise and strip leading whitespace (P32)."""
    return unicodedata.normalize("NFKC", command).strip()


def _safe_command_str(value: object) -> str | None:
    """Coerce a tool_call ``command`` field to ``str | None`` (P7)."""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return None


def tool_call_excerpt(tool_call: Mapping[str, object]) -> str:
    """Excerpt for journaling — UTF-8-safe, control-char-collapsed, key-whitelisted (P7)."""
    cmd = _safe_command_str(tool_call.get("command"))
    if cmd is not None:
        raw = cmd
    else:
        # Whitelist: never dump arbitrary keys via ``str(tool_call)``.
        # Use just ``name`` for traceability.
        name = tool_call.get("name", "<unknown>")
        raw = f"<name={name!r} command=<non-str>>"
    # NFKC + collapse control chars (except space).
    norm = unicodedata.normalize("NFKC", raw)
    cleaned = "".join(
        ch if ch == " " or not unicodedata.category(ch).startswith("C") else " " for ch in norm
    )
    # Truncate by Unicode character (slice on str is character-safe in Python).
    return cleaned[:_EXCERPT_LEN]


def is_destructive(tool_call: Mapping[str, object]) -> tuple[bool, str | None]:
    """Pure detection. v1 scope: ``Bash`` tool only (per spec AC3/D1).

    Catalogue-expansion debt: CR2B6-W1 (find -delete, shred, TRUNCATE, etc).
    """
    name = tool_call.get("name")
    if name != "Bash":
        return (False, None)
    raw_command = _safe_command_str(tool_call.get("command"))
    if raw_command is None:
        return (False, None)
    command = _normalize_command(raw_command)
    for category, pattern in _DESTRUCTIVE_TOOL_PATTERNS.items():
        if pattern.search(command):
            return (True, category)
    return (False, None)


def compute_tool_call_id(tool_call: Mapping[str, object]) -> str:
    """Stable identifier for ``--confirm-tool-call`` resume (Story 4.7, DH3a).

    CR4.7-P1: hash the SAME NFKC-normalised command ``is_destructive`` matches on,
    so the id never skews from the detection/excerpt view of the same call (a raw
    vs normalised mismatch otherwise made confirm-never-match or excerpt != id).
    """
    name_val = tool_call.get("name", "")
    name = name_val if isinstance(name_val, str) else str(name_val)
    raw_command = _safe_command_str(tool_call.get("command"))
    command = _normalize_command(raw_command) if raw_command is not None else ""
    normalized = f"{name}\0{command}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _target_from_file_delete(command: str) -> str:
    match = re.search(r"\brm\s+(?:-rf|-fr)\s+(\S+)", command)
    return match.group(1) if match else command


def _target_from_force_push(command: str) -> str:
    # CR4.7-P2: derive remote/ref from the first non-flag tokens AFTER ``push`` so
    # arg-order variants (``git push origin main --force``) no longer mis-extract
    # ``main/--force`` from the positional last-two tokens.
    min_refspec_tokens = 2
    after_push: list[str] = []
    seen_push = False
    for tok in command.split():
        if not seen_push:
            seen_push = tok == "push"
            continue
        if not tok.startswith("-"):
            after_push.append(tok)
    if len(after_push) >= min_refspec_tokens:
        return f"{after_push[0]}/{after_push[1]}"
    if after_push:
        return after_push[0]
    return command


def _target_from_drop_database(command: str) -> str:
    # CR4.7-P2: skip an optional ``IF [NOT] EXISTS`` clause so the target is the
    # real object name, not ``IF`` (``DROP TABLE IF EXISTS users`` -> ``users``).
    match = re.search(
        r"\bDROP\s+(?:DATABASE|TABLE|SCHEMA)\s+(?:IF\s+(?:NOT\s+)?EXISTS\s+)?(\S+)",
        command,
        re.IGNORECASE,
    )
    return match.group(1).rstrip(";") if match else command


def _target_from_secret_exfil(command: str) -> str:
    match = re.search(r"https?://[^\s]+", command, re.IGNORECASE)
    return match.group(0) if match else command


def extract_destructive_target(tool_call: Mapping[str, object], category: str) -> str:
    """Best-effort path/argument extraction for ``StopDecision.target`` (Story 4.7, C6)."""
    raw_command = _safe_command_str(tool_call.get("command"))
    if raw_command is None:
        return str(tool_call.get("name", "unknown"))
    command = _normalize_command(raw_command)
    extractors: dict[str, Callable[[str], str]] = {
        "file_delete": _target_from_file_delete,
        "force_push": _target_from_force_push,
        "force_push_with_lease": _target_from_force_push,
        "drop_database": _target_from_drop_database,
        "secret_exfil": _target_from_secret_exfil,
    }
    extractor = extractors.get(category)
    return extractor(command) if extractor is not None else command


def build_high_risk_reason(*, tool: str, category: str, excerpt: str) -> str:
    """Pack tool name + category + excerpt into frozen ``StopDecision.reason`` (C6)."""
    trimmed = excerpt[:120]
    return f"{tool}:{category} ({trimmed})"


def prompt_for_reconfirmation(nonce: str, category: str, excerpt: str) -> bool:
    """Synchronous TTY re-confirmation prompt (P5/P6/P22/P4).

    Returns ``True`` only when the user echoes ``nonce`` exactly (constant-time
    compare). ``EOFError`` / ``KeyboardInterrupt`` → ``False`` (reject) so
    non-interactive contexts can not silently accept.
    """
    if not nonce:
        raise ValueError("nonce must be non-empty")
    try:
        response = input(
            f"Destructive operation detected ({category}): {excerpt}\n"
            f"Type nonce to proceed: {nonce}\n> "
        )
    except (EOFError, KeyboardInterrupt):
        return False
    if not response:
        return False
    return secrets.compare_digest(response, nonce)
