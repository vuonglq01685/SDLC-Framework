"""Anti-tautology tests — schema-version enforcement + helper sanity (AC6 / PR18 / P19).

Split from ``test_harness_anti_tautology.py`` to stay under the 400-line LOC
cap (Architecture §765 + NFR-MAINT-3).

Tests covered here:
  1. schema_version drift detection — load helpers reject mismatched versions
     (PR18 — was previously enforced but untested).
  2. mock_responses_dir drift detection (PR16).
  3. Sanity asserts for ``_safe_corrupt`` itself (defense in depth).
  4. ``_canon_json`` determinism across calls.

Tier-1 CLI mutation receipt + AC6.3 + AC2.5 live in
``test_harness_anti_tautology.py``.
Tier-2 pipeline mutation receipt + mock-miss live in
``test_harness_anti_tautology_pipeline.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from e2e._anti_tautology_helpers import _safe_corrupt
from e2e.cli.conftest import load_commands_yaml
from e2e.pipeline.conftest import _canon_json, _load_pipeline_yaml

pytestmark = pytest.mark.e2e


# ===========================================================================
# AC P19 / PR18 — schema_version enforcement is exercised, not just declared
# ===========================================================================


def test_commands_yaml_schema_version_mismatch_raises(tmp_path: Path) -> None:
    """PR18 / P19 — load_commands_yaml MUST reject schema_version drift.

    Was previously enforced in code but untested; an inverse change (silently
    accepting v2) would have shipped unnoticed. Closes that anti-tautology gap.
    """
    bad_yaml = tmp_path / "commands.yaml"
    bad_yaml.write_text(
        "schema_version: 2\nscenario: x\ncommands: []\n",
        encoding="utf-8",
    )
    with pytest.raises(AssertionError) as exc_info:
        load_commands_yaml(bad_yaml)
    assert "schema_version mismatch" in str(exc_info.value), (
        f"Expected schema_version mismatch error; got:\n{exc_info.value}"
    )


def test_pipeline_yaml_schema_version_mismatch_raises(tmp_path: Path) -> None:
    """PR18 / P19 — _load_pipeline_yaml MUST reject schema_version drift."""
    bad_yaml = tmp_path / "pipeline.yaml"
    bad_yaml.write_text(
        "schema_version: 99\n"
        "scenario: x\n"
        'mock_responses_dir: "./mock_responses"\n'
        "steps:\n"
        '  - id: "01_step"\n'
        '    kind: "engine_dispatch_smoke"\n'
        '    prompt: "p"\n'
        '    workflow_step: "s"\n',
        encoding="utf-8",
    )
    with pytest.raises(AssertionError) as exc_info:
        _load_pipeline_yaml(bad_yaml)
    assert "schema_version mismatch" in str(exc_info.value), (
        f"Expected schema_version mismatch error; got:\n{exc_info.value}"
    )


def test_pipeline_yaml_mock_responses_dir_mismatch_raises(tmp_path: Path) -> None:
    """PR16 — _load_pipeline_yaml MUST reject ``mock_responses_dir`` drift.

    Field was previously declared but not validated (theatre). Now enforced.
    """
    bad_yaml = tmp_path / "pipeline.yaml"
    bad_yaml.write_text(
        "schema_version: 1\n"
        "scenario: x\n"
        'mock_responses_dir: "./other_path"\n'
        "steps:\n"
        '  - id: "01_step"\n'
        '    kind: "engine_dispatch_smoke"\n'
        '    prompt: "p"\n'
        '    workflow_step: "s"\n',
        encoding="utf-8",
    )
    with pytest.raises(AssertionError) as exc_info:
        _load_pipeline_yaml(bad_yaml)
    assert "mock_responses_dir" in str(exc_info.value), (
        f"Expected mock_responses_dir error; got:\n{exc_info.value}"
    )


# ===========================================================================
# Sanity asserts for the safe-corruption helper itself (defense in depth).
# ===========================================================================


def test_safe_corrupt_rejects_empty() -> None:
    """P4 — _safe_corrupt MUST reject empty input rather than write a sentinel."""
    with pytest.raises(AssertionError):
        _safe_corrupt(b"")


def test_safe_corrupt_rejects_invalid_utf8() -> None:
    """PR6 — _safe_corrupt MUST reject non-UTF-8-decodable input.

    Previous fallback silently produced invalid UTF-8 for non-printable inputs
    (``original + b"<<CORRUPTED>>"``). The contract now demands decodable
    input so the result is guaranteed decodable.
    """
    with pytest.raises(AssertionError) as exc_info:
        _safe_corrupt(bytes([0xFF, 0xFE, 0xFD]))
    assert "UTF-8" in str(exc_info.value), f"Expected UTF-8 error; got:\n{exc_info.value}"


def test_safe_corrupt_changes_input() -> None:
    """P4 — _safe_corrupt always returns a different byte sequence (UTF-8 valid)."""
    for sample in (b"hello", b"a", b"x\n", b"012345", b'{"k":"v"}'):
        corrupted = _safe_corrupt(sample)
        assert corrupted != sample, f"Failed to corrupt {sample!r}"
        corrupted.decode("utf-8")


def test_safe_corrupt_appends_sentinel_for_unprintable_decodable() -> None:
    """PR6 — _safe_corrupt appends ``<<CORRUPTED>>`` for decodable inputs that lack
    printable-ASCII bytes (rare; e.g., all-newline file). Result remains decodable.
    """
    # A file containing only newline bytes (0x0A — outside the 32-126 printable range
    # but fully UTF-8 decodable). The fallback branch fires.
    sample = b"\n\n\n"
    corrupted = _safe_corrupt(sample)
    assert corrupted != sample
    assert corrupted.endswith(b"<<CORRUPTED>>")
    corrupted.decode("utf-8")  # MUST remain decodable.


def test_canon_json_is_deterministic_across_calls() -> None:
    """Sanity — _canon_json must produce identical bytes for identical inputs."""
    sample = [{"b": 2, "a": 1}, {"y": "z", "x": "w"}]
    runs = [_canon_json(sample) for _ in range(5)]
    assert all(r == runs[0] for r in runs), f"Canonicalization not deterministic: {runs!r}"
    parsed = json.loads(runs[0])
    assert list(parsed[0].keys()) == ["a", "b"], "sort_keys did not reorder map keys"
