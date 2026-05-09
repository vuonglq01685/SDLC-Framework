"""`sdlc --version` handler (FR47, AC1.4)."""

from __future__ import annotations

import sdlc

__all__ = ("get_version",)


def get_version() -> str:
    """Return the canonical framework version string.

    Sourced from ``sdlc.__version__`` per ADR-001's deferred-dynamic-version
    contract; ``importlib.metadata.version("sdlc-framework")`` is asserted
    to match in CI but is not the runtime source until ADR-008's first-release
    revisit.
    """
    return sdlc.__version__
