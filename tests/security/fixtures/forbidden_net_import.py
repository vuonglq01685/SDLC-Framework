"""Anti-tautology fixture: intentionally forbidden network import."""

from __future__ import annotations

import requests


def trigger() -> str:
    return requests.__name__
