"""SDLC framework CLI surface (Story 1.16+).

Public entry point: the `sdlc` console script registered in pyproject.toml
[project.scripts] points at `sdlc.cli.main:app` (a Typer application).
Submodules are leaf consumers — the package itself does not re-export.
"""

from __future__ import annotations
