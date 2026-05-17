"""Tier-2 e2e for ``sdlc architect`` (Story 2A.14, AC10).

AC10 mandates THREE scenarios, all driven through the real MockAIRuntime
pipeline (no ``dispatch`` mock):

  1. Happy path with sub-tracks: phase 1 APPROVED + primary declares
     ``requires: [database, security]`` → ARCHITECTURE.md + 2 sub-track files;
     journal has 3 ``agent_dispatched`` + 3 ``artifact_written``.
  2. No sub-tracks (``requires:`` absent): primary declares no frontmatter →
     ARCHITECTURE.md written, ``sub-tracks/`` empty, ``sub_tracks_dispatched: []``.
  3. Unknown sub-track error: primary declares ``requires: [quantum-computing]``
     → exit 1, ``ERR_UNKNOWN_SUB_TRACK``, ARCHITECTURE.md written, no sub-track
     files.

Scenarios 2 and 3 vary the primary mock's ``requires:`` block via the
``materialize_primary_mock(requires=...)`` parameter (Story 2A.14 code review
CR14-P8/B1) so the dynamic-dispatch behaviour is exercised end-to-end, not just
in unit tests with a hand-fed ``requires:`` string.

Anti-tautology receipt (AC10 mandatory — executable form):
``test_e2e_sdlc_architect_unknown_guard_is_load_bearing`` mutates
``_SUBTRACK_SPECIALISTS`` so ``quantum-computing`` becomes a KNOWN track and
asserts scenario 3's ``ERR_UNKNOWN_SUB_TRACK`` outcome then disappears — proving
the allowlist guard, and only the guard, is what fails scenario 3. This replaces
the earlier prose-only receipt with a kept regression that re-verifies the guard
is load-bearing on every run.
"""

from __future__ import annotations

import functools
import json
import sys
import unittest.mock
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from sdlc.cli import _architect_pipeline as _ap
from sdlc.cli.architect import _SUBTRACK_SPECIALISTS
from sdlc.cli.main import app
from sdlc.signoff import ArtifactRef, SignoffRecord, write_record
from sdlc.signoff.hasher import compute_artifact_hash

pytestmark = pytest.mark.e2e

_runner = CliRunner()

_FIXTURES = Path(__file__).parent / "fixtures" / "architect"

_TS1 = "2026-05-14T09:00:00.000Z"
_TS2 = "2026-05-14T10:00:00.000Z"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _init_repo(tmp_path: Path) -> None:
    from sdlc.cli import init as init_mod

    ctx = typer.Context(command=typer.core.TyperCommand("init"))
    ctx.ensure_object(dict)
    with unittest.mock.patch.object(init_mod, "_get_repo_root_or_cwd", return_value=tmp_path):
        init_mod.run_init(ctx=ctx)


def _seed_product_md(tmp_path: Path) -> Path:
    req = tmp_path / "01-Requirement"
    req.mkdir(parents=True, exist_ok=True)
    p = req / "01-PRODUCT.md"
    p.write_bytes((_FIXTURES / "01-PRODUCT.md").read_bytes())
    return p


def _approve_phase1(tmp_path: Path, product_path: Path) -> None:
    artifact_hash = compute_artifact_hash(product_path, repo_root=tmp_path)
    record = SignoffRecord(
        phase=1,
        artifacts=(ArtifactRef(path="01-Requirement/01-PRODUCT.md", hash=artifact_hash),),
        approved_by="e2e-approver",
        approved_at=_TS2,
        drafted_at=_TS1,
        validated_at=_TS2,
    )
    write_record(record, repo_root=tmp_path)


def _invoke_architect(tmp_path: Path, *, json_mode: bool = True) -> Any:
    args = ["--json", "architect"] if json_mode else ["architect"]
    with unittest.mock.patch("sdlc.cli.architect._get_repo_root_or_cwd", return_value=tmp_path):
        return _runner.invoke(app, args)


def _invoke_with_requires(tmp_path: Path, requires: tuple[str, ...] | None) -> Any:
    """Invoke ``sdlc architect`` with the primary mock declaring ``requires``.

    Patches ``materialize_primary_mock`` so the MockAIRuntime primary response
    carries the desired ``requires:`` frontmatter while every other layer
    (parse, validate, dispatch loop, postconditions) runs for real.
    """
    patched = functools.partial(_ap.materialize_primary_mock, requires=requires)
    with (
        unittest.mock.patch("sdlc.cli.architect._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli.architect.materialize_primary_mock", patched),
    ):
        return _runner.invoke(app, ["--json", "architect"])


def _read_journal(tmp_path: Path) -> list[dict[str, Any]]:
    jp = tmp_path / ".claude" / "state" / "journal.log"
    if not jp.is_file():
        return []
    return [
        json.loads(line) for line in jp.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _sub_track_files(tmp_path: Path) -> list[Path]:
    sub_dir = tmp_path / "02-Architecture" / "02-System" / "sub-tracks"
    if not sub_dir.is_dir():
        return []
    return sorted(sub_dir.glob("*.md"))


# ---------------------------------------------------------------------------
# Scenario 1 — Happy path with sub-tracks (AC10.1)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_e2e_sdlc_architect_happy_path(tmp_path: Path) -> None:
    """AC10 scenario 1: phase 1 APPROVED → ARCHITECTURE.md + 2 sub-tracks + journal."""
    _init_repo(tmp_path)
    product_path = _seed_product_md(tmp_path)
    _approve_phase1(tmp_path, product_path)

    result = _invoke_architect(tmp_path)

    assert result.exit_code == 0, result.stdout + (result.stderr or "")

    # AC5: ARCHITECTURE.md written with non-trivial mock content
    arch_path = tmp_path / "02-Architecture" / "02-System" / "ARCHITECTURE.md"
    assert arch_path.is_file(), "ARCHITECTURE.md must be written"
    arch_text = arch_path.read_text(encoding="utf-8")
    assert "PLACEHOLDER" in arch_text, "ARCHITECTURE.md must have MockAIRuntime placeholder content"

    # AC3: both declared sub-tracks dispatched (default mock requires: [database, security])
    sub_files = _sub_track_files(tmp_path)
    assert [f.name for f in sub_files] == ["database.md", "security.md"]
    for f in sub_files:
        content = f.read_text(encoding="utf-8")
        assert "PLACEHOLDER" in content, f"{f.name}: must have MockAIRuntime placeholder content"

    # AC10.1: journal has exactly 3 agent_dispatched + 3 artifact_written
    entries = _read_journal(tmp_path)
    dispatched = [e for e in entries if e["kind"] == "agent_dispatched"]
    written = [e for e in entries if e["kind"] == "artifact_written"]
    assert len(dispatched) == 3, "journal must have primary + database + security dispatch"
    assert len(written) == 3, "journal must have artifact_written for each dispatch"
    assert any(e["payload"]["specialist"] == "system-architect" for e in dispatched)
    for e in written:
        assert e["actor"] == "cli"
        assert e["after_hash"].startswith("sha256:")
        assert e["payload"]["phase"] == 2

    # AC1: emit_json success envelope
    out = json.loads(result.stdout)
    assert out["phase"] == 2
    assert out["track"] == "architect"
    assert out["specialist"] == "system-architect"
    assert out["outcome"] == "success"
    assert out["architecture_path"] == "02-Architecture/02-System/ARCHITECTURE.md"
    assert sorted(out["sub_tracks_dispatched"]) == ["database", "security"]
    assert len(out["sub_track_artifacts"]) == len(out["sub_tracks_dispatched"])


# ---------------------------------------------------------------------------
# Scenario 2 — No sub-tracks: requires: absent (AC10.2)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_e2e_sdlc_architect_no_sub_tracks(tmp_path: Path) -> None:
    """AC10 scenario 2: primary declares no frontmatter → ARCHITECTURE.md, no sub-tracks."""
    _init_repo(tmp_path)
    product_path = _seed_product_md(tmp_path)
    _approve_phase1(tmp_path, product_path)

    result = _invoke_with_requires(tmp_path, requires=None)

    assert result.exit_code == 0, result.stdout + (result.stderr or "")

    arch_path = tmp_path / "02-Architecture" / "02-System" / "ARCHITECTURE.md"
    assert arch_path.is_file(), "ARCHITECTURE.md must be written"

    # No sub-track files
    assert _sub_track_files(tmp_path) == [], "sub-tracks/ must be empty with no requires:"

    # AC10.2: journal has exactly 1 agent_dispatched + 1 artifact_written (primary only)
    entries = _read_journal(tmp_path)
    assert len([e for e in entries if e["kind"] == "agent_dispatched"]) == 1
    assert len([e for e in entries if e["kind"] == "artifact_written"]) == 1

    out = json.loads(result.stdout)
    assert out["outcome"] == "success"
    assert out["sub_tracks_dispatched"] == []
    assert out["sub_track_artifacts"] == []


# ---------------------------------------------------------------------------
# Scenario 3 — Unknown sub-track error (AC10.3)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_e2e_sdlc_architect_unknown_sub_track(tmp_path: Path) -> None:
    """AC10 scenario 3: primary declares requires: [quantum-computing] → exit 1, no sub-tracks."""
    _init_repo(tmp_path)
    product_path = _seed_product_md(tmp_path)
    _approve_phase1(tmp_path, product_path)

    result = _invoke_with_requires(tmp_path, requires=("quantum-computing",))

    assert result.exit_code == 1
    output = result.stdout + (result.stderr or "")
    assert "ERR_UNKNOWN_SUB_TRACK" in output
    assert "quantum-computing" in output

    # ARCHITECTURE.md IS written (primary dispatch succeeded before validation)
    arch_path = tmp_path / "02-Architecture" / "02-System" / "ARCHITECTURE.md"
    assert arch_path.is_file()

    # No sub-track files, no sub-track dispatch entries
    assert _sub_track_files(tmp_path) == []
    entries = _read_journal(tmp_path)
    dispatched = [e for e in entries if e["kind"] == "agent_dispatched"]
    assert len(dispatched) == 1, "only the primary dispatch must be journalled"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_e2e_sdlc_architect_unknown_guard_is_load_bearing(tmp_path: Path) -> None:
    """AC10 anti-tautology receipt (executable form).

    Mutation: extend ``_SUBTRACK_SPECIALISTS`` so ``quantum-computing`` becomes a
    KNOWN sub-track, mapped to an already-registered specialist. With the
    allowlist guard thus neutralised, the scenario-3 input MUST no longer raise
    ``ERR_UNKNOWN_SUB_TRACK`` — proving that guard, and only that guard, is what
    fails scenario 3. If this test ever passes while
    ``test_e2e_sdlc_architect_unknown_sub_track`` also passes unchanged, the
    scenario-3 assertion has become tautological and must be re-examined.
    """
    _init_repo(tmp_path)
    product_path = _seed_product_md(tmp_path)
    _approve_phase1(tmp_path, product_path)

    mutated = MappingProxyType({**_SUBTRACK_SPECIALISTS, "quantum-computing": "system-architect"})
    patched = functools.partial(_ap.materialize_primary_mock, requires=("quantum-computing",))
    with (
        unittest.mock.patch("sdlc.cli.architect._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli.architect.materialize_primary_mock", patched),
        unittest.mock.patch("sdlc.cli.architect._SUBTRACK_SPECIALISTS", mutated),
    ):
        result = _runner.invoke(app, ["--json", "architect"])

    # Guard neutralised → the unknown-sub-track error path is no longer reached.
    output = result.stdout + (result.stderr or "")
    assert "ERR_UNKNOWN_SUB_TRACK" not in output, (
        "anti-tautology breach: scenario 3 still surfaces ERR_UNKNOWN_SUB_TRACK "
        "even with the _SUBTRACK_SPECIALISTS guard neutralised"
    )


# ---------------------------------------------------------------------------
# Extra — Phase gate block (not an AC10 scenario; defence-in-depth)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_e2e_sdlc_architect_phase_gate_block(tmp_path: Path) -> None:
    """Phase 1 AWAITING_SIGNOFF → ERR_PHASE1_NOT_APPROVED; no files written."""
    _init_repo(tmp_path)
    _seed_product_md(tmp_path)
    # No signoff record → AWAITING_SIGNOFF

    result = _invoke_architect(tmp_path)

    assert result.exit_code == 1
    assert "ERR_PHASE1_NOT_APPROVED" in (result.stdout + (result.stderr or ""))

    # No architecture files must be written
    arch_dir = tmp_path / "02-Architecture" / "02-System"
    if arch_dir.exists():
        assert not (arch_dir / "ARCHITECTURE.md").is_file(), (
            "ARCHITECTURE.md must not be written when gate blocks"
        )
    # No dispatch journalled
    entries = _read_journal(tmp_path)
    assert [e for e in entries if e["kind"] == "agent_dispatched"] == []
