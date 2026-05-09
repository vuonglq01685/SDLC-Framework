"""Shared agent_runs.jsonl reader for cli/trace.py and cli/logs.py."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)


def iter_agent_runs(path: Path) -> Iterator[dict[str, Any]]:
    """Yield records from agent_runs.jsonl.

    Missing file → empty iterator. Malformed line → WARNING + skip.
    """
    # Open eagerly so a vanished file (TOCTOU between exists/open) is treated
    # the same as "missing → empty" instead of bubbling FileNotFoundError.
    try:
        fh = path.open("r", encoding="utf-8")
    except FileNotFoundError:
        return
    except OSError as exc:
        raise OSError(f"agent_runs read failed at {path}: {exc}") from exc
    with fh:
        for lineno, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                raw: object = json.loads(stripped)
            except json.JSONDecodeError as exc:
                _logger.warning(
                    "malformed agent_runs line at %s:%d: %s — skipping",
                    path,
                    lineno,
                    exc,
                )
                continue
            if not isinstance(raw, dict):
                _logger.warning(
                    "non-object agent_runs line at %s:%d (got %s) — skipping",
                    path,
                    lineno,
                    type(raw).__name__,
                )
                continue
            yield raw
