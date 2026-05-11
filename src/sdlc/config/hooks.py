"""Hook registry loader — AC2, AC11 D1, Story 2A.4.

D-decision: AC11 chose D1 (new src/sdlc/config/hooks.py) because it respects
existing module boundaries (config/ already owns pyproject parsing per
Architecture §1057) and keeps hooks/runner.py pure.

Reads [tool.sdlc.hooks] pre_write from pyproject.toml and validates hook names
against the known builtin set. Fails loud at construction time on unknown or
duplicate hooks (Architecture §1109: no silent skips).

Boundary (AC9): this module imports only stdlib + sdlc.errors.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import tomllib  # type: ignore[import-not-found]  # stdlib 3.11+; CI/pre-commit use 3.12

from sdlc.errors import ConfigError

_KNOWN_HOOKS: Final[frozenset[str]] = frozenset({"naming_validator", "phase_gate"})


def load_hook_registry(pyproject_path: Path) -> tuple[str, ...]:
    """Load the pre_write hook list from pyproject.toml [tool.sdlc.hooks].

    Returns:
        Ordered tuple of hook names (empty tuple if the section is absent).

    Raises:
        ConfigError: if pyproject.toml is not found, contains unknown hooks,
            or contains duplicate hook names.
    """
    if not pyproject_path.exists():
        raise ConfigError(
            f"pyproject.toml not found at {pyproject_path}",
            details={"path": str(pyproject_path), "step": "load_hook_registry"},
        )

    try:
        with pyproject_path.open("rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(
            f"pyproject.toml is not valid TOML: {exc}",
            details={"path": str(pyproject_path), "step": "load_hook_registry"},
        ) from exc

    hook_section = data.get("tool", {}).get("sdlc", {}).get("hooks", {})
    raw_list: list[str] = hook_section.get("pre_write", [])

    if not raw_list:
        return ()

    # Validate — no-I/O check first (two-pass per Story 2A.2 pattern)
    seen: set[str] = set()
    for name in raw_list:
        if name in seen:
            raise ConfigError(
                f"duplicate hook in pre_write registry: {name!r}",
                details={"hook": name, "step": "validate_hook_registry"},
            )
        seen.add(name)
        if name not in _KNOWN_HOOKS:
            available = sorted(_KNOWN_HOOKS)
            raise ConfigError(
                f"unknown hook in pyproject.toml [tool.sdlc.hooks].pre_write: {name!r};"
                f" available: {available!r}",
                details={
                    "hook": name,
                    "available": available,
                    "step": "validate_hook_registry",
                },
            )

    return tuple(raw_list)
