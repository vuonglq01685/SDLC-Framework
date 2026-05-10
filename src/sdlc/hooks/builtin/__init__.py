"""Builtin hook implementations for the pre-write hook chain (Story 2A.4).

Public re-exports of the 2 builtin hooks per AC8:
- naming_validator: validates artifact ids against canonical regexes (FR36, AC4)
- phase_gate: validates phase boundary signoff exists (FR37, AC5)
"""

from __future__ import annotations

from sdlc.hooks.builtin.naming_validator import naming_validator
from sdlc.hooks.builtin.phase_gate import phase_gate

__all__ = ["naming_validator", "phase_gate"]
