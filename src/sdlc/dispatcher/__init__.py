"""Dispatcher public API — primary dispatch, panel orchestration, retry (FR25-FR27, NFR-REL-4).

Architecture §821-§824, §1067.
Consumers (engine, CLI) import ONLY from this module.
"""

from __future__ import annotations

from sdlc.dispatcher._hook_chain import build_pre_write_hook_chain
from sdlc.dispatcher.core import (
    DispatchOutcome,
    DispatchResult,
    PanelResult,
    dispatch,
    dispatch_panel,
)
from sdlc.dispatcher.retry import with_retries

__all__: tuple[str, ...] = (
    "DispatchOutcome",
    "DispatchResult",
    "PanelResult",
    "build_pre_write_hook_chain",
    "dispatch",
    "dispatch_panel",
    "with_retries",
)
