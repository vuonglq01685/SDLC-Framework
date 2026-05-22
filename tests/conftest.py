"""Pytest configuration: add scripts/ to sys.path for test imports."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make scripts/ importable so tests can do `import check_module_boundaries`.
_scripts_dir = str(Path(__file__).resolve().parents[1] / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)


@pytest.fixture(autouse=True)
def _sdlc_mock_runtime_for_cli_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep CLI integration/e2e on MockAIRuntime after the ADR-029 default-flip.

    Sets the explicit ``SDLC_MOCK_GATE_BYPASS`` opt-in so the ``--allow-mock``
    gate is waived in tests without production code detecting pytest (Story 2B.1
    review P16). Tests that exercise the gate's exit-1 path delete it explicitly.
    """
    monkeypatch.setenv("SDLC_USE_MOCK_RUNTIME", "1")
    monkeypatch.setenv("SDLC_MOCK_GATE_BYPASS", "1")
