"""Dispatcher public API — primary dispatch, panel orchestration, retry (FR25-FR27, NFR-REL-4).

Architecture §821-§824, §1067.
Consumers (engine, CLI) import ONLY from this module.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from sdlc.dispatcher._hook_chain import build_pre_write_hook_chain

# P2 (code review): promote journal-emit helpers to public API so consumers
# (e.g., cli/research.py) do not have to reach into _panel_helpers private
# names; the leading-underscore module remains the source of truth.
from sdlc.dispatcher._panel_helpers import (
    _allocate_seq as allocate_seq,
)
from sdlc.dispatcher._panel_helpers import (
    _content_hash as content_hash,
)
from sdlc.dispatcher._panel_helpers import (
    _make_journal_entry as make_journal_entry,
)
from sdlc.dispatcher._panel_helpers import (
    _now_ts as now_ts,
)
from sdlc.dispatcher.core import (
    DispatchOutcome,
    DispatchResult,
    PanelResult,
    dispatch,
    dispatch_panel,
)
from sdlc.dispatcher.prompts import (
    BOUNDARY_LINE,
    phase1_compound_prompt_builder,
    phase1_prompt_builder,
)
from sdlc.dispatcher.retry import with_retries

_EMPTY_EXTRA_CONTEXT: Mapping[str, object] = MappingProxyType({})


@dataclass(frozen=True)
class PanelObserver:
    """CLI-observable callbacks/context for a panel dispatch (Story 2A.8 D1-C).

    Keeps :func:`dispatch_panel` domain-pure by lifting the CLI-specific concerns
    (slash-command tagging, idea text passthrough, journal-emit gating, frontmatter
    payload) into a single typed object. ``extra_context`` is a read-only mapping
    forwarded to the ``prompt_builder`` (used for synthesizer frontmatter fields,
    D3-A). ``emit_agent_dispatched`` defaults to True for production CLI flows;
    unit-test fixtures pass an observer with ``emit_agent_dispatched=False`` to
    avoid journal noise.
    """

    slash_command: str | None = None
    idea_text: str | None = None
    extra_context: Mapping[str, object] = field(default_factory=lambda: _EMPTY_EXTRA_CONTEXT)
    emit_agent_dispatched: bool = True


__all__: tuple[str, ...] = (
    "BOUNDARY_LINE",
    "DispatchOutcome",
    "DispatchResult",
    "PanelObserver",
    "PanelResult",
    "allocate_seq",
    "build_pre_write_hook_chain",
    "content_hash",
    "dispatch",
    "dispatch_panel",
    "make_journal_entry",
    "now_ts",
    "phase1_compound_prompt_builder",
    "phase1_prompt_builder",
    "with_retries",
)
