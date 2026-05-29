"""Integration-test collection hooks (Story 2B.3 cross-runtime ordering).

The mock-vs-claude byte-identity assertion lives in a regular test
(``test_cross_runtime_byte_identity`` in ``test_abstraction_adequacy.py``), NOT in a
``pytest_sessionfinish`` hook. A hook that raised ``AssertionError`` surfaced as a fragile,
version-dependent INTERNALERROR rather than a normal test failure (review P30 / D1=b). Spec
AC2/D2 explicitly allows EITHER a session-finalize hook OR a final test ordered after both
parametrized runs; we choose the latter here. This module only guarantees the ordering: the
cross-runtime test must run AFTER both parametrized ``test_abstraction_adequacy_pipeline``
runs have populated the capture registry.
"""

from __future__ import annotations

import pytest

_CROSS_RUNTIME_TEST_NAME = "test_cross_runtime_byte_identity"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Move the cross-runtime identity test to the end of collection (review P30).

    Guarantees both parametrized conformance runs record their bytes before the
    cross-runtime comparison reads them, regardless of file or collection order.
    """

    def _is_cross_runtime(item: pytest.Item) -> bool:
        # originalname is the unparametrized function name (pytest.Function); fall back to
        # name for any non-Function item. The cross-runtime test is not parametrized.
        return getattr(item, "originalname", item.name) == _CROSS_RUNTIME_TEST_NAME

    cross_runtime = [item for item in items if _is_cross_runtime(item)]
    if not cross_runtime:
        return
    others = [item for item in items if not _is_cross_runtime(item)]
    items[:] = others + cross_runtime
