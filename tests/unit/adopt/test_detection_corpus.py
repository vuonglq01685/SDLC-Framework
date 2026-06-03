"""Golden corpus CI gate for Pass 1 detection (Story 3.2, AC6).

Runs `detect_existing` against each brownfield fixture under `tests/fixtures/brownfield/` with
a deterministic stubbed git signal (no live `git log`), and compares the canonical
`detected[]` JSON to `<fixture>/goldens/detection.json` via `_compare_one_golden`.

Usage:
  # Run normally (assert):
  pytest tests/unit/adopt/test_detection_corpus.py

  # Regenerate goldens (write):
  pytest tests/unit/adopt/test_detection_corpus.py --update-goldens

After regenerating, cite the regen in the PR Change Log (ADR-027 ceremony).

The git_signal is stubbed deterministic per fixture so goldens are reproducible across
machines and CI environments (no live `git log` in corpus tests).
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Any

import pytest

from sdlc.adopt.passes.detection import detect_existing
from sdlc.contracts.adopt_report import DetectedArtifact

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures" / "brownfield"

# All 7 fixtures (union of epics.md:1811 and epic-3-dag.md:148,183)
_FIXTURE_NAMES = [
    "java-maven-service",
    "node-npm",
    "python-pyproject",
    "go-module",
    "monorepo-submodules",
    "preexisting-symlinks",
    "greenfield-disguised",
]

# Recency-OFF corpus: the stub is intentionally EMPTY so no +5 boost is applied and the goldens
# pin the base (recency-independent) confidences — byte-stable across machines. In a real run the
# CLI layer reads live git log; the recency-ON branch (which production always runs) is pinned
# separately by the deterministic recency-ON variant below (`_recency_on_signal`).
_STUB_GIT_SIGNAL: dict[str, int] = {}  # empty = no recency boost, stable across all machines

# Recency-ON variant: treat every detected path as touched this many days ago (≤ 90 ⇒ +5 boost).
_RECENT_DAYS = 5


# ---------------------------------------------------------------------------
# Canonical JSON helper (mirrors tests/e2e/pipeline/_golden_assert.py:_canon_json)
# ---------------------------------------------------------------------------


def _canon_json(obj: Any) -> str:
    """Canonical JSON string for human-reviewable goldens (PR-DR6 sanctioned deviation)."""
    return (
        json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), indent=2) + "\n"
    )


def _artifacts_to_json(artifacts: list[DetectedArtifact]) -> Any:
    """Serialize detected artifacts to a stable JSON-serializable list (sorted by path)."""
    return sorted(
        [
            {
                "confidence": a.confidence,
                "kind": a.kind,
                "path": a.path,
                "suggested_target": a.suggested_target,
            }
            for a in artifacts
        ],
        key=lambda x: x["path"],
    )


# ---------------------------------------------------------------------------
# Golden helpers (mirrors tests/e2e/cli/conftest.py:282-391)
# ---------------------------------------------------------------------------

_ACTION_HINT = (
    "action: review the diff. If intentional, regenerate via "
    "'pytest tests/unit/adopt/test_detection_corpus.py --update-goldens' "
    "and cite the change in the PR Change Log."
)


def _compare_one_golden(
    filename: str,
    actual: str,
    goldens_dir: Path,
) -> str | None:
    """Return an error string if golden mismatches, or None if it matches."""
    golden_path = goldens_dir / filename
    if not golden_path.exists():
        return f"Golden file missing: {golden_path}\n{_ACTION_HINT}"
    expected = golden_path.read_text(encoding="utf-8")
    if actual == expected:
        return None
    diff = "".join(
        difflib.unified_diff(
            expected.splitlines(keepends=True),
            actual.splitlines(keepends=True),
            fromfile=f"expected/{filename}",
            tofile=f"actual/{filename}",
        )
    )
    return f"GOLDEN MISMATCH: {golden_path}\n{diff}\n{_ACTION_HINT}"


def _assert_or_update_golden(
    fixture_dir: Path,
    actual_json: str,
    update: bool,
    filename: str = "detection.json",
) -> None:
    goldens_dir = fixture_dir / "goldens"
    goldens_dir.mkdir(parents=True, exist_ok=True)
    if update:
        (goldens_dir / filename).write_text(actual_json, encoding="utf-8")
        return
    err = _compare_one_golden(filename, actual_json, goldens_dir)
    if err:
        raise AssertionError(err)


def _recency_on_signal(fixture_dir: Path) -> dict[str, int]:
    """Deterministic recency-ON signal: every detected path treated as touched 5 days ago.

    Built from the recency-OFF detection so it depends ONLY on fixture content (no live git),
    exercising the +5 boost branch (AC3) that the empty `_STUB_GIT_SIGNAL` never triggers. This
    pins the recency-ON confidences that production always emits (`cli/adopt.py` always calls
    `git_last_touched_days`), complementing the recency-OFF `detection.json` golden.
    """
    base = detect_existing(fixture_dir, git_signal=_STUB_GIT_SIGNAL)
    return {a.path: _RECENT_DAYS for a in base}


# ---------------------------------------------------------------------------
# Parametrized corpus tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def update_goldens(request: pytest.FixtureRequest) -> bool:
    return bool(request.config.getoption("--update-goldens", default=False))


@pytest.mark.parametrize("fixture_name", _FIXTURE_NAMES)
def test_corpus_fixture_matches_golden(
    fixture_name: str,
    update_goldens: bool,
) -> None:
    """For each fixture, detect_existing output must match the stored golden."""
    fixture_dir = _FIXTURES_DIR / fixture_name
    assert fixture_dir.exists(), f"Fixture directory missing: {fixture_dir}"

    artifacts = detect_existing(fixture_dir, git_signal=_STUB_GIT_SIGNAL)
    actual_json = _canon_json(_artifacts_to_json(artifacts))
    _assert_or_update_golden(fixture_dir, actual_json, update_goldens)


@pytest.mark.parametrize("fixture_name", _FIXTURE_NAMES)
def test_corpus_fixture_recency_on_matches_golden(
    fixture_name: str,
    update_goldens: bool,
) -> None:
    """Recency-ON variant (AC3): every detected path touched ≤90d gets the +5 boost.

    Pins the recency-ON branch that production always runs, so a regression in the boost-merge
    logic surfaces in the byte-stable corpus gate (not only in the unit tests). Complements the
    recency-OFF `detection.json` golden with `detection_recent.json`.
    """
    fixture_dir = _FIXTURES_DIR / fixture_name
    assert fixture_dir.exists(), f"Fixture directory missing: {fixture_dir}"

    signal = _recency_on_signal(fixture_dir)
    artifacts = detect_existing(fixture_dir, git_signal=signal)
    actual_json = _canon_json(_artifacts_to_json(artifacts))
    _assert_or_update_golden(
        fixture_dir, actual_json, update_goldens, filename="detection_recent.json"
    )


def test_greenfield_disguised_returns_empty(update_goldens: bool) -> None:
    """Greenfield-disguised fixture must produce detected: [] (AC5)."""
    fixture_dir = _FIXTURES_DIR / "greenfield-disguised"
    assert fixture_dir.exists(), f"Fixture directory missing: {fixture_dir}"

    artifacts = detect_existing(fixture_dir, git_signal=_STUB_GIT_SIGNAL)
    assert artifacts == [], f"Greenfield-disguised fixture must return [], got: {artifacts}"


# ---------------------------------------------------------------------------
# AC7 — source-untouched: corpus detection must not modify any source file
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fixture_name", _FIXTURE_NAMES)
def test_corpus_detection_is_read_only(fixture_name: str) -> None:
    """Running detect_existing on a fixture must not create/modify any source file."""
    fixture_dir = _FIXTURES_DIR / fixture_name

    # Record all non-golden files and their mtimes before detection
    before: dict[str, float] = {}
    for p in fixture_dir.rglob("*"):
        if p.is_file() and "goldens" not in p.parts:
            before[str(p)] = p.stat().st_mtime

    detect_existing(fixture_dir, git_signal=_STUB_GIT_SIGNAL)

    # Verify: no new non-golden files appeared outside .claude/
    after_files = {
        str(p)
        for p in fixture_dir.rglob("*")
        if p.is_file() and "goldens" not in p.parts and ".claude" not in p.parts
    }
    new_files = after_files - set(before.keys())
    assert not new_files, f"detect_existing created unexpected files in {fixture_name}: {new_files}"
