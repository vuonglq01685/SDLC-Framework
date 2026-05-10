"""Workflow loader and validation module (Story 2A.1).

Public API:
    load_workflow(path: Path) -> WorkflowSpec
    validate_workflow(spec: WorkflowSpec) -> None
    WorkflowRegistry

Architecture §1063: imported by engine/, dispatcher/. Direct calls to
load_workflow outside of workflows/ and tests are a code-review-blocking pattern.
Use WorkflowRegistry as the entrypoint for engine code.
"""

from __future__ import annotations

from sdlc.workflows.loader import load_workflow
from sdlc.workflows.registry import WorkflowRegistry
from sdlc.workflows.static_check import validate_workflow

__all__ = (
    "WorkflowRegistry",
    "load_workflow",
    "validate_workflow",
)
