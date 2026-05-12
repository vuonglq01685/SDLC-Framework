"""Mock verifier verdict for `sdlc verify` v1 (Story 2A.10).

Houses the v1 deterministic mock verdict + test-only override hook used by
:mod:`sdlc.cli._verify_dispatch`'s ``_materialize_verifier_fixture``. Real
Claude dispatch (Story 2B.x) replaces the call site; the override hook
parameterises AC9 scenario #6 (verifier-failed verdict) without monkey-
patching a module-level ``Final[Mapping]``.

Extracted from ``_verify_dispatch.py`` (PC6 + LOC-cap split, post-review
2026-05-12 Cluster C-J) so that the dispatch module stays under the
Architecture §1052-§1112 / NFR-MAINT-3 400-LOC cap once the post-review
ceremony wrappers landed there.

Private CLI-internal — NOT exported via :mod:`sdlc.cli.verify`.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

__all__ = (
    "MOCK_VERIFIER_VERDICT",
    "resolve_mock_verdict",
    "set_mock_verdict_override",
)

# v1 mock verifier output (deterministic; see Story 2A.10 D2). Private: the
# on-disk frontmatter row is the public surface, NOT the verdict envelope.
MOCK_VERIFIER_VERDICT: Final[Mapping[str, str]] = MappingProxyType(
    {"verdict": "verified", "note": "v1 mock verifier - replaced by Story 2B.x"},
)

# PC6 / E14 (post-review 2026-05-12 Cluster C-J): test-only override hook.
# AC9 scenario #6 (verifier-failed verdict) needs to inject a `{"verdict":
# "failed"}` mock response; the module-level `Final[Mapping]` above is
# immutable. Tests set this module global via ``set_mock_verdict_override``
# and the dispatcher's fixture builder consults ``resolve_mock_verdict``
# instead of the Final default. Production code paths never set this.
_TEST_MOCK_VERDICT_OVERRIDE: Mapping[str, str] | None = None


def set_mock_verdict_override(verdict: Mapping[str, str] | None) -> None:
    """Test-only: override the mock verifier verdict for a single test.

    PC6/E14 hook for parameterising AC9 scenario #6 (verifier-failed) and
    DC10 (verifier-decided non-zero exit). Pass ``None`` to clear. Never
    call from production code — the default ``Final`` constant is the
    contract.
    """
    global _TEST_MOCK_VERDICT_OVERRIDE  # noqa: PLW0603 — test-only override hook
    _TEST_MOCK_VERDICT_OVERRIDE = verdict


def resolve_mock_verdict() -> Mapping[str, str]:
    """Return the active mock verdict (test override or production default)."""
    return (
        _TEST_MOCK_VERDICT_OVERRIDE
        if _TEST_MOCK_VERDICT_OVERRIDE is not None
        else MOCK_VERIFIER_VERDICT
    )
