"""Story 3.8 — authoring receipts for the net-new `characterization-author` Phase-3 specialist.

D1=(a): a NEW specialist (the shipped `tdd-strategist` is an incompatible strategy-layer advisor).
The characterization-test author is dispatched at the `pending` stage for `characterization-test`
tasks. It captures current behavior and emits `{files, tests_status: "green"}` under `tests/**`.
Mirrors the 2B.10 Phase-3 authoring invariants for a single new file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.dispatcher.prompts import BOUNDARY_LINE
from sdlc.specialists import load_registry

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[3]
_AGENTS = _REPO / "src" / "sdlc" / "agents"

_NAME = "characterization-author"
_GREEN_CONTRACT_KEYWORDS: tuple[str, ...] = ('"files"', '"tests_status"', '"green"')


def test_characterization_author_loads_via_registry() -> None:
    reg = load_registry(_AGENTS)
    assert _NAME in reg.names(), (
        f"{_NAME!r} not registered — author phase3/{_NAME}.md + add the index.yaml row."
    )


def test_characterization_author_phase_is_3() -> None:
    s = load_registry(_AGENTS).get(_NAME)
    assert s.phase == 3


def test_characterization_author_file_stem_matches_name() -> None:
    s = load_registry(_AGENTS).get(_NAME)
    assert s.frontmatter.name == _NAME
    assert s.frontmatter.schema_version == 1


def test_characterization_author_model_is_sonnet() -> None:
    s = load_registry(_AGENTS).get(_NAME)
    assert s.frontmatter.model == "sonnet"


def test_characterization_author_declares_empty_tools() -> None:
    s = load_registry(_AGENTS).get(_NAME)
    assert tuple(s.frontmatter.tools) == ()


def test_characterization_author_writes_under_tests() -> None:
    s = load_registry(_AGENTS).get(_NAME)
    assert any("tests/" in g for g in s.frontmatter.write_globs), s.frontmatter.write_globs


def test_characterization_author_body_has_no_boundary_line() -> None:
    s = load_registry(_AGENTS).get(_NAME)
    assert BOUNDARY_LINE not in s.body


def test_characterization_author_declares_green_contract() -> None:
    """The pending-stage gate for characterization tasks requires tests_status=='green'."""
    s = load_registry(_AGENTS).get(_NAME)
    missing = [kw for kw in _GREEN_CONTRACT_KEYWORDS if kw not in s.body]
    assert not missing, f"body missing GREEN-contract keywords {missing!r}"


def test_characterization_author_body_has_no_placeholder_marker() -> None:
    s = load_registry(_AGENTS).get(_NAME)
    lowered = s.body.lower()
    for marker in ("placeholder", "replaced by story", "tbd"):
        assert marker not in lowered, f"body still contains placeholder marker {marker!r}"


def test_characterization_author_in_all_phase3_names_set() -> None:
    """The shared 2B.10 Phase-3 invariant sweep must include the new specialist."""
    from unit.specialists.test_phase3_2b10_authoring import _ALL_PHASE3_NAMES

    assert _NAME in _ALL_PHASE3_NAMES
