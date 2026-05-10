"""Latency benchmark: Claude-side hook round-trip ≤ 500ms p95 (AC7, Story 2A.6).

Measures end-to-end wall-clock: Claude-side pre_tool_use.py → subprocess sdlc hook-check
→ JSON response parse.  Uses pytest-benchmark pedantic mode for explicit warmup control.

Two budgets enforced:
  - Write/Edit tools (chain path): p95 ≤ 500ms over 10 runs (2 warmup).
  - Read/Bash tools (fast-path):  p95 ≤  50ms over 10 runs (2 warmup).

Run in isolation on the dedicated CI job:  pytest -m parity_perf
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PRE_TOOL_USE = (
    Path(__file__).parent.parent.parent / "src" / "sdlc" / "claude_hooks" / "pre_tool_use.py"
)

_PYPROJECT_HOOK_REGISTRY = """\
[tool.sdlc.hooks]
pre_write = ["naming_validator", "phase_gate"]
"""

_CHAIN_BUDGET_MS = 500
_FAST_PATH_BUDGET_MS = 50


def _run_hook(envelope: dict, cwd: Path) -> dict:
    """Invoke pre_tool_use.py as subprocess; return parsed stdout JSON."""
    import subprocess

    result = subprocess.run(
        [sys.executable, str(_PRE_TOOL_USE)],
        input=json.dumps(envelope).encode(),
        capture_output=True,
        cwd=str(cwd),
        timeout=10.0,
    )
    raw = result.stdout.strip()
    if not raw:
        raise RuntimeError(f"no stdout; stderr: {result.stderr!r}")
    return json.loads(raw)


@pytest.fixture()
def hook_repo(tmp_path: Path) -> Path:
    """Minimal repo layout: pyproject.toml only (phase-1 path is always-allow)."""
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT_HOOK_REGISTRY, encoding="utf-8")
    return tmp_path


@pytest.mark.parity_perf
def test_chain_latency_p95(benchmark, hook_repo: Path) -> None:
    """Full round-trip (Write → chain) must complete p95 ≤ 500ms."""
    envelope = {
        "tool_name": "Write",
        "tool_input": {"file_path": "01-Requirement/04-Epics/EPIC-perf-test.json"},
        "cwd": str(hook_repo),
    }

    result = benchmark.pedantic(
        _run_hook,
        kwargs={"envelope": envelope, "cwd": hook_repo},
        warmup_rounds=2,
        rounds=10,
        iterations=1,
    )

    assert result.get("decision") in ("approve", "block"), f"unexpected envelope: {result}"

    p95_ms = benchmark.stats.get("p95", benchmark.stats["max"]) * 1000
    assert p95_ms <= _CHAIN_BUDGET_MS, (
        f"chain round-trip p95={p95_ms:.0f}ms exceeds budget of {_CHAIN_BUDGET_MS}ms"
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
        _run_hook,
        kwargs={"envelope": envelope, "cwd": hook_repo},
        warmup_rounds=2,
        rounds=10,
        iterations=1,
    )

    assert result.get("decision") == "approve", f"fast-path must approve: {result}"

    p95_ms = benchmark.stats.get("p95", benchmark.stats["max"]) * 1000
    assert p95_ms <= _FAST_PATH_BUDGET_MS, (
        f"fast-path p95={p95_ms:.0f}ms exceeds budget of {_FAST_PATH_BUDGET_MS}ms"
    )
