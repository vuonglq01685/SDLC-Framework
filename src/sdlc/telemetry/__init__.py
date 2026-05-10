"""Telemetry package — agent run records, future DORA + debug streams (Architecture §888-§892).

2A.3: ``runs.py`` (``agent_runs.jsonl`` placeholder writer).
2B+: ``debug.py``, ``dora.py``, ``correlation.py`` will be added here.
"""

from __future__ import annotations

from sdlc.telemetry.runs import record_agent_run

__all__ = ["record_agent_run"]
