"""Story 2A.8 AC8 — Phase 1 specialist stubs load from package agents tree."""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.specialists import load_registry

_REPO = Path(__file__).resolve().parents[3]
_AGENTS = _REPO / "src" / "sdlc" / "agents"

pytestmark = pytest.mark.unit


def test_phase1_specialists_load_via_registry() -> None:
    reg = load_registry(_AGENTS)
    for name in (
        "product-strategist",
        "technical-researcher",
        "devil-advocate",
        "requirement-synthesizer",
    ):
        s = reg.get(name)
        assert s.phase == 1
        globs = s.frontmatter.write_globs
        assert "01-Requirement/01-PRODUCT.md" in globs
