"""Story 3.8 AC6 — brownfield Phase-3 mock-vs-claude byte-identity conformance.

Extends the 2B.3 abstraction-adequacy contract to the net-new ``characterization-author``: its
real authored prompt body is dispatched through both ``MockAIRuntime`` and ``ClaudeAIRuntime``
(via the deterministic claude stub) and the runtime-neutral ``AgentResult`` must be byte-identical.

Invariant (mirrors test_abstraction_adequacy.py): do NOT add a third ``_RUNTIME_FACTORIES`` entry;
build a self-contained single-row fixture; do not touch the seed goldens.

POSIX-only: the claude stub installs an executable on PATH.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Final

import pytest

from integration._abstraction_adequacy_helpers import _format_diff, install_claude_stub_on_path
from sdlc.runtime import AgentResult, ClaudeAIRuntime, MockAIRuntime

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="POSIX-only: claude stub installs an executable on PATH",
    ),
]

_BROWNFIELD_PHASE3_REPRESENTATIVE: Final[str] = "characterization-author"


def test_characterization_author_dispatched_byte_identical_mock_vs_claude(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC6: the brownfield characterization-author prompt body is byte-identical mock-vs-claude."""
    import yaml

    from sdlc.runtime.mock import compute_prompt_hash
    from sdlc.specialists import load_registry

    agents_dir = Path(__file__).resolve().parents[2] / "src" / "sdlc" / "agents"
    spec = load_registry(agents_dir).get(_BROWNFIELD_PHASE3_REPRESENTATIVE)
    prompt = spec.body
    workflow_step = "phase3-brownfield-conformance"
    context = {"workflow_step": workflow_step}

    fixture_row = {
        compute_prompt_hash(prompt): {
            "output_text": "phase3-brownfield characterization artifact",
            "tokens_in": 9,
            "tokens_out": 13,
        }
    }
    fixtures_dir = tmp_path / "mock_responses"
    fixtures_dir.mkdir()
    fixture_path = fixtures_dir / f"{workflow_step}.yaml"
    fixture_path.write_text(
        yaml.safe_dump(fixture_row, sort_keys=True, allow_unicode=True),
        encoding="utf-8",
    )

    mock_rt = MockAIRuntime(fixtures_dir=fixtures_dir)
    install_claude_stub_on_path(monkeypatch, fixture_path, tmp_path)
    claude_rt = ClaudeAIRuntime()

    async def _dispatch_all() -> tuple[AgentResult, AgentResult, AgentResult]:
        m1 = await mock_rt.dispatch(prompt, context)
        m2 = await mock_rt.dispatch(prompt, context)
        c = await claude_rt.dispatch(prompt, context)
        return m1, m2, c

    mock_1, mock_2, claude_result = asyncio.run(_dispatch_all())

    assert mock_1.model_dump(mode="json") == mock_2.model_dump(mode="json"), (
        "non-deterministic dispatch of the characterization-author prompt"
    )

    def _neutral(result: AgentResult) -> dict[str, object]:
        return {k: v for k, v in result.model_dump(mode="json").items() if k != "mock"}

    assert _neutral(mock_1) == _neutral(claude_result), _format_diff(
        f"AgentResult ({_BROWNFIELD_PHASE3_REPRESENTATIVE}: mock vs claude)",
        json.dumps(_neutral(mock_1), sort_keys=True).encode("utf-8"),
        json.dumps(_neutral(claude_result), sort_keys=True).encode("utf-8"),
    )
    assert mock_1.mock is True and claude_result.mock is False
