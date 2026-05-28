"""Clean fixture without forbidden network imports."""

from __future__ import annotations


def local_only() -> str:
    return "ok"
