"""Shared helpers for the KPI Strip live-poller Playwright suites (Story 5.17).

Split out of ``test_dashboard_kpi_strip_live.py`` to keep each behavioral-witness
module under the 400-LOC/file cap (NFR-MAINT-3, Architecture §765). Holds the
``/api/dora`` payload builders, the route mock, and the DOM selectors shared by
the core (``test_dashboard_kpi_strip_live.py``) and hardening
(``test_dashboard_kpi_strip_live_hardening.py``) test modules. Not a test module
(no ``test_`` prefix) so pytest does not collect it.
"""

from __future__ import annotations

import json
from typing import Any

_LIVE_FIXTURE = "/static/components/kpi-strip/kpi-strip-live.fixture.html"
_TARGET = "#kpi-strip-live-target"
_STRIP = f"{_TARGET} .kpi-strip"
_CELLS = f"{_TARGET} .kpi-strip__cell"
_NO_DATA_VALUES = f"{_TARGET} .kpi-strip__value--no-data"
_CELL1_DELTA_UP = f"{_TARGET} .kpi-strip__cell:nth-child(1) .kpi-strip__delta--up"
_CELL2_DELTA_NEUTRAL = f"{_TARGET} .kpi-strip__cell:nth-child(2) .kpi-strip__delta--neutral"
_CELL4_DELTA_UP = f"{_TARGET} .kpi-strip__cell:nth-child(4) .kpi-strip__delta--up"
_CELL4_DELTA_DOWN = f"{_TARGET} .kpi-strip__cell:nth-child(4) .kpi-strip__delta--down"


def _metric(
    *,
    data_status: str = "ok",
    value: float | int | None = 1,
    per_day: float | None = None,
    unit: str = "hours",
    failed_count: int | None = None,
    total_count: int | None = None,
    recovery_count: int | None = None,
) -> dict[str, Any]:
    if data_status == "insufficient_data":
        return {
            "data_status": "insufficient_data",
            "value": None,
            "unit": unit,
            **({"per_day": None} if per_day is not None or unit == "deploys_per_window" else {}),
            **({"failed_count": None, "total_count": None} if unit == "ratio" else {}),
            **({"recovery_count": None} if recovery_count is not None or unit == "hours" else {}),
        }
    payload: dict[str, Any] = {"data_status": "ok", "value": value, "unit": unit}
    if unit == "deploys_per_window":
        payload["per_day"] = per_day if per_day is not None else float(value) / 7
    if unit == "ratio":
        payload["failed_count"] = failed_count
        payload["total_count"] = total_count
    if unit == "hours" and recovery_count is not None:
        payload["recovery_count"] = recovery_count
    return payload


def _dora_payload(
    *,
    deploy_7d: dict[str, Any] | None = None,
    lead_7d: dict[str, Any] | None = None,
    cfr_7d: dict[str, Any] | None = None,
    mttr_7d: dict[str, Any] | None = None,
    deploy_30d: dict[str, Any] | None = None,
    lead_30d: dict[str, Any] | None = None,
    cfr_30d: dict[str, Any] | None = None,
    mttr_30d: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "windows": {
            "7d": {
                "deployment_frequency": deploy_7d
                or _metric(value=7, unit="deploys_per_window", per_day=2.4),
                "lead_time": lead_7d or _metric(value=18, unit="hours"),
                "change_failure_rate": cfr_7d
                or _metric(value=0.25, unit="ratio", failed_count=1, total_count=4),
                "mttr": mttr_7d or _metric(value=2.0, unit="hours", recovery_count=2),
            },
            "30d": {
                "deployment_frequency": deploy_30d
                or _metric(value=30, unit="deploys_per_window", per_day=1.8),
                "lead_time": lead_30d or _metric(value=21, unit="hours"),
                "change_failure_rate": cfr_30d
                or _metric(value=0.30, unit="ratio", failed_count=3, total_count=10),
                "mttr": mttr_30d or _metric(value=2.8, unit="hours", recovery_count=5),
            },
        },
    }


def _mock_dora_route(page: object, payload: dict[str, Any]) -> None:
    body = json.dumps(payload)

    def handler(route: object) -> None:
        route.fulfill(  # type: ignore[attr-defined]
            status=200,
            content_type="application/json",
            body=body,
        )

    page.route("**/api/dora", handler)  # type: ignore[attr-defined]
