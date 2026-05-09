"""CI lint: assert migration registry is consistent with CURRENT_SCHEMA_VERSION.

For every integer N in [2, CURRENT_SCHEMA_VERSION], asserts a matching
src/sdlc/migrations/v<N>.py exists and exports a valid migrate(state) callable.
For v1 builds (CURRENT_SCHEMA_VERSION=1), the chain check is a no-op.

Exit codes: 0 = consistent, 1 = inconsistent (gap, missing, or invalid script).
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """Run the migration registry consistency lint."""
    from sdlc.errors import SchemaError  # noqa: PLC0415
    from sdlc.migrations import discover_migrations, load_migration  # noqa: PLC0415
    from sdlc.state.reader import CURRENT_SCHEMA_VERSION  # noqa: PLC0415

    errors: list[str] = []
    warnings: list[str] = []

    expected = list(range(2, CURRENT_SCHEMA_VERSION + 1))
    actual = discover_migrations()

    # Chain completeness: every integer in [2, CURRENT_SCHEMA_VERSION] must have a script.
    for n in expected:
        if n not in actual:
            msg = f"missing migration script: migrations/v{n}.py"
            print(msg, file=sys.stderr)
            errors.append(msg)

    # Contract validation: every discovered script must export a valid migrate callable.
    for n in actual:
        try:
            load_migration(n)
        except SchemaError as e:
            msg = f"invalid migration script v{n}: {e.message}"
            print(msg, file=sys.stderr)
            errors.append(msg)

    # Extra scripts beyond CURRENT_SCHEMA_VERSION are unusual — flag as warning only.
    extras = [n for n in actual if n > CURRENT_SCHEMA_VERSION]
    for n in extras:
        msg = (
            f"warning: migrations/v{n}.py exists but"
            f" CURRENT_SCHEMA_VERSION={CURRENT_SCHEMA_VERSION}; extra script"
        )
        print(msg, file=sys.stderr)
        warnings.append(msg)

    if errors:
        return 1

    print(
        f"migration registry OK: CURRENT_SCHEMA_VERSION={CURRENT_SCHEMA_VERSION}, scripts={actual}",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
