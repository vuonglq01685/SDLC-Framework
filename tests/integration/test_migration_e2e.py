"""Integration tests for schema-gate refusal and migrate command E2E (AC8, Story 1.19)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_SKIP_NO_UV = pytest.mark.skipif(
    shutil.which("uv") is None,
    reason="uv not on PATH — skipping subprocess e2e test",
)

_VALID_V1_STATE: dict[str, object] = {
    "schema_version": 1,
    "next_monotonic_seq": 0,
    "epics": {},
    "stories": {},
    "tasks": {},
    "phase": 1,
}


def _write_state(project_root: Path, payload: dict[str, object]) -> Path:
    state_dir = project_root / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / "state.json"
    state_file.write_text(json.dumps(payload), encoding="utf-8")
    (state_dir / "journal.log").touch()
    return state_file


def _run_sdlc(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "sdlc", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


# ---------------------------------------------------------------------------
# AC8.1 — sdlc status refuses v2+ state with a helpful message
# ---------------------------------------------------------------------------


@_SKIP_NO_UV
def test_sdlc_status_refuses_v2_state(tmp_path: Path) -> None:
    """sdlc status must exit non-zero and mention 'sdlc migrate-v<N>' for v2+ state."""
    _write_state(tmp_path, {**_VALID_V1_STATE, "schema_version": 2})

    result = _run_sdlc(["status"], tmp_path)

    assert result.returncode != 0, (
        f"Expected non-zero exit for v2 state; got 0.\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    combined = result.stdout + result.stderr
    assert "schema_version" in combined or "migrate" in combined, (
        f"Error message must mention schema_version or migrate.\ncombined={combined}"
    )


@_SKIP_NO_UV
def test_sdlc_status_accepts_v1_state(tmp_path: Path) -> None:
    """sdlc status must succeed (exit 0) for a valid v1 state."""
    _write_state(tmp_path, _VALID_V1_STATE)

    result = _run_sdlc(["status"], tmp_path)

    assert result.returncode == 0, (
        f"Expected exit 0 for v1 state.\nstdout={result.stdout}\nstderr={result.stderr}"
    )


# ---------------------------------------------------------------------------
# AC8.2 — sdlc status error message contains 'sdlc migrate-vN' hint
# ---------------------------------------------------------------------------


@_SKIP_NO_UV
def test_sdlc_status_error_mentions_migrate_command(tmp_path: Path) -> None:
    _write_state(tmp_path, {**_VALID_V1_STATE, "schema_version": 2})

    result = _run_sdlc(["status"], tmp_path)

    combined = result.stdout + result.stderr
    assert "sdlc migrate-v" in combined or "migrate-v2" in combined, (
        f"Error output must contain 'sdlc migrate-v'; got:\n{combined}"
    )


# ---------------------------------------------------------------------------
# AC8.3 — migrate-vN command registered when migration scripts discovered
#         (v1 build = no scripts → command absent from help)
# ---------------------------------------------------------------------------


@_SKIP_NO_UV
def test_migrate_commands_absent_for_v1_build(tmp_path: Path) -> None:
    """For a v1 build with no migration scripts, migrate-vN must not appear in help."""
    result = _run_sdlc(["--help"], tmp_path)

    assert result.returncode == 0
    assert "migrate-v" not in result.stdout, (
        f"No migration scripts exist, but migrate-vN appeared in help:\n{result.stdout}"
    )


# ---------------------------------------------------------------------------
# AC8.4 — sdlc status returns non-zero for malformed JSON
# ---------------------------------------------------------------------------


@_SKIP_NO_UV
def test_sdlc_status_refuses_malformed_json(tmp_path: Path) -> None:
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text("not-json", encoding="utf-8")
    (state_dir / "journal.log").touch()

    result = _run_sdlc(["status"], tmp_path)

    assert result.returncode != 0, (
        f"Expected non-zero for malformed JSON.\nstdout={result.stdout}\nstderr={result.stderr}"
    )


# ---------------------------------------------------------------------------
# AC8.5 — schema_version 0 is also refused (not a valid v1 state)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Note: No subprocess test for the happy-path sdlc migrate-vN execution exists
# because this is a v1 build with no migration scripts. The run_migrate
# orchestrator is covered by unit tests in tests/unit/cli/test_migrate.py with
# mocked dependencies. When v2 migration scripts ship, add an E2E test here.
# ---------------------------------------------------------------------------


@_SKIP_NO_UV
def test_sdlc_status_refuses_v0_state(tmp_path: Path) -> None:
    _write_state(tmp_path, {**_VALID_V1_STATE, "schema_version": 0})

    result = _run_sdlc(["status"], tmp_path)

    assert result.returncode != 0, (
        f"Expected non-zero for v0 state.\nstdout={result.stdout}\nstderr={result.stderr}"
    )
