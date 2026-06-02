"""End-to-end smoke tests for the wire-format lock ceremony (Story 1.21, AC7.4).

Runs the full pipeline via subprocess to verify the freeze script and immutability
pytest gate both exit 0 on a clean repo with committed snapshots, AND that drift
detection actually exits 1 via subprocess (P21 — the gate's primary purpose).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only invariants in repo state"),
]

_REPO_ROOT: Path = Path(__file__).resolve().parents[2]


def test_freeze_script_exits_0_on_clean_repo() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/freeze_wireformat_snapshots.py"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"freeze_wireformat_snapshots.py exited {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "6 contracts match snapshots" in result.stdout


def test_immutability_pytest_gate_exits_0() -> None:
    # --no-cov is a justified workaround for the project's global --cov-fail-under=90;
    # script coverage is exercised by the unit tests at tests/unit/scripts/ and by
    # test_freeze_script_exits_1_on_drift below (which actually drives the script).
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/contracts/test_wireformat_immutability.py",
            "-v",
            "--no-cov",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"pytest tests/contracts/test_wireformat_immutability.py exited {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_freeze_script_exits_1_on_drift(tmp_path: Path) -> None:
    """P21: drift detection actually exits 1 via subprocess (not just unit-level).

    Stages a copy of the freeze script in tmp_path, materialises 5 valid snapshots,
    mutates one to force drift, then invokes the script with cwd=tmp_path. The
    script's `_REPO_ROOT = Path(__file__).resolve().parent.parent` resolves to
    tmp_path, so the snapshot lookup hits the staged (mutated) fixtures rather than
    the real repo tree.
    """
    # Stage the script in tmp_path/scripts/.
    script_src = _REPO_ROOT / "scripts" / "freeze_wireformat_snapshots.py"
    script_dst = tmp_path / "scripts" / "freeze_wireformat_snapshots.py"
    script_dst.parent.mkdir(parents=True, exist_ok=True)
    script_dst.write_bytes(script_src.read_bytes())

    # Materialise valid snapshots, then corrupt one.
    from sdlc.contracts import _WIRE_FORMAT_REGISTRY

    snapshot_dir = tmp_path / "tests" / "contract_snapshots" / "v1"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    for slug, model_cls in _WIRE_FORMAT_REGISTRY:
        path = snapshot_dir / f"{slug}.json"
        if slug == "journal_entry":
            path.write_bytes(b'{"stale":"drift_marker"}\n')
        else:
            schema = model_cls.model_json_schema(mode="serialization")
            path.write_bytes(
                json.dumps(
                    schema,
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    indent=2,
                ).encode("utf-8")
                + b"\n"
            )

    result = subprocess.run(
        [sys.executable, str(script_dst)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, (
        f"freeze_wireformat_snapshots.py expected exit 1 (drift) but got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "wireformat-immutability drift" in result.stderr
    assert "journal_entry" in result.stderr
