"""Latency benchmark: Claude-side hook round-trip ≤ 500ms p95 (AC7, Story 2A.6).

Measures end-to-end wall-clock: Claude-side pre_tool_use.py → subprocess sdlc hook-check
→ JSON response parse.  Uses pytest-benchmark pedantic mode for explicit warmup control.

Two budgets enforced:
  - Write/Edit tools (chain path): p95 ≤ 500ms over 10 runs (2 warmup).
  - Read/Bash tools (fast-path):  p95 ≤  50ms over 10 runs (2 warmup).

Run in isolation on the dedicated CI job:  pytest -m parity_perf

Implements:
  - AC7 (cold-start ≤ 500ms wall-clock per Claude Code call).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from _clihelper import venv_path_env

_PRE_TOOL_USE = (
    Path(__file__).parent.parent.parent / "src" / "sdlc" / "claude_hooks" / "pre_tool_use.py"
)

_PYPROJECT_HOOK_REGISTRY = """\
[tool.sdlc.hooks]
pre_write = ["naming_validator", "phase_gate"]
"""

_CHAIN_BUDGET_MS = 500
_FAST_PATH_BUDGET_MS = 50


def _run_hook(envelope: dict, cwd: Path) -> tuple[dict, str]:
    """Invoke pre_tool_use.py as subprocess; return (parsed_stdout, stderr_text)."""
    result = subprocess.run(
        [sys.executable, str(_PRE_TOOL_USE)],
        input=json.dumps(envelope).encode(),
        capture_output=True,
        cwd=str(cwd),
        env=venv_path_env(),  # pin the inner `sdlc hook-check` to the editable venv CLI
        timeout=10.0,
    )
    raw = result.stdout.strip()
    if not raw:
        raise RuntimeError(f"no stdout; stderr: {result.stderr!r}")
    parsed = json.loads(raw)
    stderr_text = result.stderr.decode("utf-8", errors="replace")
    return parsed, stderr_text


def _run_hook_decision_only(envelope: dict, cwd: Path) -> dict:
    """Benchmark-friendly wrapper returning only the parsed decision."""
    parsed, _ = _run_hook(envelope, cwd)
    return parsed


def _percentile(values: list[float], pct: float) -> float:
    """Compute pct-th percentile (0..1) using nearest-rank with linear interpolation.

    F13 fix: pytest-benchmark Stats does not always expose a 'p95' key; computing
    from raw data avoids the fragile ``.get("p95", ["max"])`` fallback that would
    silently degrade the gate to a max-budget if the API drifts.
    """
    if not values:
        raise ValueError("cannot compute percentile of empty list")
    ordered = sorted(values)
    idx = pct * (len(ordered) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(ordered) - 1)
    frac = idx - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


@pytest.fixture()
def hook_repo(tmp_path: Path) -> Path:
    """Minimal repo layout: pyproject.toml only (phase-1 path is always-allow)."""
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT_HOOK_REGISTRY, encoding="utf-8")
    return tmp_path


def _assert_engine_actually_invoked(envelope: dict, cwd: Path) -> None:
    """Pre-bench sanity: confirm the chain actually executes (not silent fail-open).

    F11 fix: if ``sdlc`` is not on PATH, pre_tool_use.py fail-opens and emits
    approve without ever running the engine. The bench would then measure
    fail-open latency instead of chain latency. Assert no '[pre_tool_use WARN]'
    appears in stderr — that string is only emitted on the fail-open path.
    """
    parsed, stderr_text = _run_hook(envelope, cwd)
    if "[pre_tool_use WARN]" in stderr_text:
        raise AssertionError(
            "latency benchmark would measure fail-open path (sdlc not invoked); "
            f"stderr indicates fail-open:\n{stderr_text}"
        )
    # Sanity: a phase-1 EPIC path on a workspace with the registry must allow.
    assert parsed["decision"] == "approve", (
        f"sanity check expected approve, got {parsed!r} (stderr: {stderr_text!r})"
    )


@pytest.mark.parity_perf
def test_chain_latency_p95(benchmark, hook_repo: Path) -> None:
    """Full round-trip (Write → chain) must complete p95 ≤ 500ms."""
    envelope = {
        "tool_name": "Write",
        "tool_input": {"file_path": "01-Requirement/04-Epics/EPIC-perf-test.json"},
        "cwd": str(hook_repo),
    }

    # F11: Pre-bench sanity check that the chain is actually exercised.
    _assert_engine_actually_invoked(envelope, hook_repo)

    result = benchmark.pedantic(
        _run_hook_decision_only,
        kwargs={"envelope": envelope, "cwd": hook_repo},
        warmup_rounds=2,
        rounds=10,
        iterations=1,
    )

    # F12: tighten — EPIC-perf-test.json is phase-1, must allow. If we got block,
    # the chain is misbehaving and the bench is meaningless.
    assert result["decision"] == "approve", f"chain must approve perf-test path: {result}"

    # F13: compute p95 from raw timings, not via the fragile dict fallback.
    timings = list(benchmark.stats["data"])
    p95_ms = _percentile(timings, 0.95) * 1000
    assert p95_ms <= _CHAIN_BUDGET_MS, (
        f"chain round-trip p95={p95_ms:.0f}ms exceeds budget of {_CHAIN_BUDGET_MS}ms "
        f"(timings: {[f'{t * 1000:.0f}' for t in timings]})"
    )


@pytest.mark.parity_perf
def test_fast_path_latency_p95(benchmark, hook_repo: Path) -> None:
    """Fast-path (Read → no subprocess) must complete p95 ≤ 50ms."""
    envelope = {
        "tool_name": "Read",
        "tool_input": {"file_path": "docs/readme.md"},
        "cwd": str(hook_repo),
    }

    result = benchmark.pedantic(
        _run_hook_decision_only,
        kwargs={"envelope": envelope, "cwd": hook_repo},
        warmup_rounds=2,
        rounds=10,
        iterations=1,
    )

    assert result["decision"] == "approve", f"fast-path must approve: {result}"

    # F13: compute p95 from raw timings.
    timings = list(benchmark.stats["data"])
    p95_ms = _percentile(timings, 0.95) * 1000
    assert p95_ms <= _FAST_PATH_BUDGET_MS, (
        f"fast-path p95={p95_ms:.0f}ms exceeds budget of {_FAST_PATH_BUDGET_MS}ms "
        f"(timings: {[f'{t * 1000:.0f}' for t in timings]})"
    )
