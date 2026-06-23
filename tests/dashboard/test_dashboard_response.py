"""Performance benchmark for ``GET /state.json`` (Story 5.1 AC2 / NFR-PERF-3)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_UNIT_DASHBOARD = Path(__file__).resolve().parents[1] / "unit" / "dashboard"
if str(_UNIT_DASHBOARD) not in sys.path:
    sys.path.insert(0, str(_UNIT_DASHBOARD))

from _http import http_get  # noqa: E402

pytestmark = [pytest.mark.benchmark, pytest.mark.unit]


def test_state_json_p50_under_100ms(benchmark, running_dashboard) -> None:
    base_url, port, _ = running_dashboard

    def _fetch() -> int:
        status, _, _ = http_get(base_url, "/state.json", port=port)
        return status

    result = benchmark(_fetch)
    assert result == 200
    assert benchmark.stats.stats.median < 0.1
