"""Pytest configuration: add scripts/ to sys.path for test imports.

Registers shared pytest options used across all test tiers:
  --update-goldens  Regenerate golden files in place instead of asserting equality.
                    Consumed by e2e CLI/pipeline corpus tests and the unit-tier
                    brownfield corpus tests (Story 3.2 AC6).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make scripts/ importable so tests can do `import check_module_boundaries`.
_scripts_dir = str(Path(__file__).resolve().parents[1] / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

# Make tests/ importable so tests can do `import _clihelper` (shared subprocess-CLI helpers).
_tests_dir = str(Path(__file__).resolve().parent)
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-goldens",
        action="store_true",
        default=False,
        help="Regenerate golden files in place instead of asserting equality.",
    )


@pytest.fixture(autouse=True)
def _sdlc_mock_runtime_for_cli_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep CLI integration/e2e on MockAIRuntime after the ADR-029 default-flip.

    Sets the explicit ``SDLC_MOCK_GATE_BYPASS`` opt-in so the ``--allow-mock``
    gate is waived in tests without production code detecting pytest (Story 2B.1
    review P16). Tests that exercise the gate's exit-1 path delete it explicitly.
    """
    monkeypatch.setenv("SDLC_USE_MOCK_RUNTIME", "1")
    monkeypatch.setenv("SDLC_MOCK_GATE_BYPASS", "1")


@pytest.fixture(autouse=True)
def _sdlc_claude_compat_default_bypass(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure the Claude compat gate stays bypassed by default in tests (Story 2B.2 D1).

    The gate auto-bypasses under pytest (``PYTEST_CURRENT_TEST`` is set), so this
    fixture just clears any leaked ``SDLC_TEST_FORCE_COMPAT_CHECK`` value from a
    prior test or developer shell. Tests that exercise the real gate (e.g. the
    ``claude_version_gate`` matrix) re-set the force env var via their own fixture.
    """
    monkeypatch.delenv("SDLC_TEST_FORCE_COMPAT_CHECK", raising=False)
