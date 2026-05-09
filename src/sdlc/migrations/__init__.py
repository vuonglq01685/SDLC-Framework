"""Schema migration registry — this module IS the complete registry (FR49, ADR-022).

No separate registry.py exists; discover_migrations() and load_migration() live here.
Migration scripts are siblings: src/sdlc/migrations/v<N>.py exporting
`def migrate(state: dict[str, Any]) -> dict[str, Any]`. They are auto-
discovered by discover_migrations() and dispatched by cli/migrate.py.

No migration scripts ship in v1 — CURRENT_SCHEMA_VERSION (state/reader.py)
is 1; this module is the substrate that future v2+ work plugs into.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import re
from collections.abc import Callable
from typing import Any, Final

from sdlc.errors import SchemaError
from sdlc.state.reader import CURRENT_SCHEMA_VERSION

_VERSION_FILENAME_REGEX: Final[re.Pattern[str]] = re.compile(r"^v(?P<n>[1-9][0-9]*)$")

__all__ = (
    "CURRENT_SCHEMA_VERSION",
    "discover_migrations",
    "load_migration",
)


def discover_migrations() -> list[int]:
    """Return sorted ascending list of available migration version numbers.

    Inspects filenames only — no module imports. Cold-start budget: < 5 ms.
    Files not matching ^v<N>.py (e.g. _helpers.py, __init__.py) are silently ignored.
    """
    import sdlc.migrations as _self  # noqa: PLC0415

    versions: list[int] = []
    for module_info in pkgutil.iter_modules(_self.__path__):
        m = _VERSION_FILENAME_REGEX.match(module_info.name)
        if m:
            versions.append(int(m.group("n")))
    return sorted(set(versions))


def load_migration(n: int) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Load and validate the migrate callable from migrations/v<N>.py.

    Raises SchemaError if the script is missing or does not export a valid
    migrate(state: dict) -> dict callable.
    """
    available = discover_migrations()
    if n not in available:
        raise SchemaError(
            f"no migration script for v{n}; available: {available}",
            details={"code": "ERR_MIGRATION_NOT_FOUND", "requested": n, "available": available},
        )

    mod = importlib.import_module(f"sdlc.migrations.v{n}")
    migrate_fn = getattr(mod, "migrate", None)

    if not callable(migrate_fn):
        raise SchemaError(
            f"migrations/v{n}.py does not export a valid migrate(state: dict) -> dict callable",
            details={"code": "ERR_MIGRATION_INVALID", "version": n, "reason": "missing-callable"},
        )

    try:
        sig = inspect.signature(migrate_fn)
        positional = [
            p
            for p in sig.parameters.values()
            if p.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]
        if len(positional) != 1:
            raise ValueError("wrong number of positional params")
    except (ValueError, TypeError) as e:
        raise SchemaError(
            f"migrations/v{n}.py does not export a valid migrate(state: dict) -> dict callable",
            details={"code": "ERR_MIGRATION_INVALID", "version": n, "reason": "wrong-signature"},
        ) from e

    return migrate_fn  # type: ignore[no-any-return]
