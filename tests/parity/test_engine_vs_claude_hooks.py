"""Parity gate: engine-side run_hook_chain vs Claude-side pre_tool_use.py (AC5, Story 2A.6).

For every fixture row in hook_parity_v1.yaml BOTH layers must return the SAME decision
(allow/deny) and the SAME error_code. A fixture-coverage assertion enforces ≥ 20 rows.

Engine-side: calls run_hook_chain(payload, hooks=(naming_validator, phase_gate), ...)
  directly in-process.
Claude-side: invokes src/sdlc/claude_hooks/pre_tool_use.py as a subprocess (which in
  turn shells out to ``sdlc hook-check``), reads the JSON envelope from stdout.

Both sides run against an isolated tmp_path that acts as the repo root:
  - A minimal pyproject.toml (with hook registry) is created in tmp_path.
  - Signoff YAML files from repo_setup_steps are written to
    tmp_path/.claude/state/signoffs/.
  - The pre_tool_use.py subprocess is launched with cwd=tmp_path so that
    ``sdlc hook-check`` inherits that working directory and falls back to tmp_path
    (not the real git root) when git rev-parse fails on a non-repo directory.

Architecture §1067 (dispatcher → hooks allowed), §1109 (hooks ↛ engine/dispatcher).
Decision D2: parity test IS the e2e for Story 2A.6 (no separate Tier-1 fixture).
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from sdlc.hooks.builtin.naming_validator import naming_validator
from sdlc.hooks.builtin.phase_gate import phase_gate
from sdlc.hooks.payload import build_write_intent_payload
from sdlc.hooks.runner import HookDecision, run_hook_chain

# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "hook_parity_v1.yaml"
_MIN_FIXTURE_ROWS = 20


def _load_fixture_rows() -> list[dict[str, Any]]:
    with _FIXTURE_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)  # type: ignore[return-value]


_ROWS: list[dict[str, Any]] = _load_fixture_rows()


def test_fixture_corpus_minimum() -> None:
    """Guard: fixture file must contain ≥ 20 rows — prevents accidental deletion."""
    count = len(_ROWS)
    if count < _MIN_FIXTURE_ROWS:
        pytest.fail(f"fixture corpus shrunk below {_MIN_FIXTURE_ROWS} rows (got {count})")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PYPROJECT_HOOK_REGISTRY = """\
[tool.sdlc.hooks]
pre_write = ["naming_validator", "phase_gate"]
"""

_SIGNOFF_DIR = Path(".claude/state/signoffs")


def _setup_repo(tmp_path: Path, steps: list[dict[str, Any]]) -> None:
    """Create the minimal repo layout needed by hook_check (pyproject.toml + signoffs)."""
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT_HOOK_REGISTRY, encoding="utf-8")
    for step in steps:
        if step["kind"] == "create_signoff":
            phase = step["phase"]
            approved = step["approved"]
            signoff_dir = tmp_path / _SIGNOFF_DIR
            signoff_dir.mkdir(parents=True, exist_ok=True)
            signoff_file = signoff_dir / f"phase-{phase}.yaml"
            signoff_file.write_text(f"approved: {str(approved).lower()}\n", encoding="utf-8")


def _expand_target_path(row: dict[str, Any], tmp_path: Path) -> tuple[str, str]:
    """Return (relative_path, envelope_file_path) for engine-side and Claude-side.

    relative_path: POSIX-relative path used in HookPayload.target_path.
    envelope_file_path: value passed as tool_input.file_path in the Claude envelope;
        may be absolute for path-shape tests.
    """
    raw = row["target_path"]

    if row.get("path_is_absolute_under_cwd"):
        # Absolute path under tmp_path — tests _resolve_path in pre_tool_use.py
        abs_path = str(tmp_path / raw)
        return raw, abs_path  # engine gets relative; Claude gets absolute

    if row.get("path_is_absolute_outside_repo"):
        # Absolute path outside tmp_path — triggers path_outside_repo deny
        outside = str(tmp_path.parent / "parity-outside" / raw)
        return raw, outside  # engine-side not used (claude_only); Claude gets absolute

    return raw, raw  # both get the same relative path


def _make_phase_gate_hook(repo_root: Path):  # type: ignore[return]
    """Phase gate closure with __is_phase_gate__ marker for bypass detection."""

    def _hook(p):  # type: ignore[no-untyped-def]
        return phase_gate(p, repo_root=repo_root)

    _hook.__is_phase_gate__ = True  # type: ignore[attr-defined]
    return _hook


def _run_engine_side(relative_path: str, tmp_path: Path) -> HookDecision:
    """Run naming_validator + phase_gate chain in-process; return the decision."""
    payload = build_write_intent_payload(
        hook_name="pre_write",
        target_path=relative_path,
        write_intent="dispatcher_artifact_write",
    )
    hooks = (naming_validator, _make_phase_gate_hook(tmp_path))
    return asyncio.run(run_hook_chain(payload, hooks=hooks, journal_path=None))


_PRE_TOOL_USE = (
    Path(__file__).parent.parent.parent / "src" / "sdlc" / "claude_hooks" / "pre_tool_use.py"
)


def _run_claude_side(envelope_file_path: str, tool_name: str, tmp_path: Path) -> dict[str, Any]:
    """Run pre_tool_use.py as a subprocess; parse and return its stdout JSON."""
    envelope = {
        "tool_name": tool_name,
        "tool_input": {"file_path": envelope_file_path},
        "cwd": str(tmp_path),
    }
    result = subprocess_run_helper(envelope, tmp_path)
    raw = result.stdout.strip()
    if not raw:
        pytest.fail(f"pre_tool_use.py produced no stdout; stderr: {result.stderr!r}")
    return json.loads(raw)  # type: ignore[return-value]


def subprocess_run_helper(envelope: dict[str, Any], cwd: Path):  # type: ignore[return]
    """Wrap subprocess.run to keep the import at top-level."""
    import subprocess

    return subprocess.run(
        [sys.executable, str(_PRE_TOOL_USE)],
        input=json.dumps(envelope).encode(),
        capture_output=True,
        cwd=str(cwd),
        timeout=30.0,
    )


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------


def _assert_engine(decision: HookDecision, row: dict[str, Any]) -> None:
    expected = row["expected_decision"]
    expected_code = row["expected_error_code"]
    assert decision.decision == expected, (
        f"[engine] {row['name']}: expected decision={expected!r}, got {decision.decision!r}"
    )
    assert decision.error_code == expected_code, (
        f"[engine] {row['name']}: expected error_code={expected_code!r},"
        f" got {decision.error_code!r}"
    )


def _assert_claude(envelope: dict[str, Any], row: dict[str, Any]) -> None:
    expected = row["expected_decision"]
    expected_code = row["expected_error_code"]
    # Map engine vocabulary → Claude vocabulary
    expected_claude = "approve" if expected == "allow" else "block"
    assert envelope.get("decision") == expected_claude, (
        f"[claude] {row['name']}: expected decision={expected_claude!r},"
        f" got {envelope.get('decision')!r}"
    )
    if expected_code is not None:
        assert envelope.get("error_code") == expected_code, (
            f"[claude] {row['name']}: expected error_code={expected_code!r},"
            f" got {envelope.get('error_code')!r}"
        )


# ---------------------------------------------------------------------------
# Parametrized parity test
# ---------------------------------------------------------------------------


@pytest.mark.parity
@pytest.mark.parametrize("row", _ROWS, ids=[r["name"] for r in _ROWS])
def test_parity(row: dict[str, Any], tmp_path: Path) -> None:
    """Both hook layers must agree on decision + error_code for every fixture row."""
    _setup_repo(tmp_path, row.get("repo_setup_steps") or [])
    relative_path, envelope_file_path = _expand_target_path(row, tmp_path)

    # ── engine-side ────────────────────────────────────────────────────────
    if not row.get("claude_only") and not row.get("engine_skip"):
        decision = _run_engine_side(relative_path, tmp_path)
        _assert_engine(decision, row)

    # ── claude-side ────────────────────────────────────────────────────────
    claude_env = _run_claude_side(envelope_file_path, row["tool_name"], tmp_path)
    _assert_claude(claude_env, row)
