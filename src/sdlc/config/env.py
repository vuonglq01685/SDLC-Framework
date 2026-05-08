from __future__ import annotations

import os
from typing import Final

from sdlc.errors import ConfigError

ENV_PREFIX_ALLOWLIST: Final[tuple[str, ...]] = ("SDLC_", "CLAUDE_")
ENV_EXACT_ALLOWLIST: Final[frozenset[str]] = frozenset({"GH_TOKEN"})


def read_env(name: str) -> str | None:
    """Return the env-var value if ``name`` matches the allow-list, else raise ConfigError.

    Allow-list per Architecture §671 + NFR-SEC-2 (prd.md:798):
    - prefix matches: SDLC_*, CLAUDE_*
    - exact matches: GH_TOKEN (consumed only by the pr-author specialist)

    Returns None for allowed-but-unset env vars (legitimate "not configured" signal).
    Raises ConfigError for forbidden reads.
    """
    if not _is_allowed(name):
        raise ConfigError(
            f"env var {name!r} not in allow-list (SDLC_*, CLAUDE_*, GH_TOKEN)",
            details={"name": name},
        )
    return os.environ.get(name)


def _is_allowed(name: str) -> bool:
    if name in ENV_EXACT_ALLOWLIST:
        return True
    return any(name.startswith(prefix) for prefix in ENV_PREFIX_ALLOWLIST)
