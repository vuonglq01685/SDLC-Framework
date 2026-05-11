"""Tier-2 e2e: `sdlc research` (Story 2A.9, AC11)."""

from __future__ import annotations

import json
import sys
import unittest.mock
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from sdlc.cli.main import app
from sdlc.dispatcher.prompts import BOUNDARY_LINE

_runner = CliRunner()

pytestmark = pytest.mark.e2e

_RESEARCH_GOLDEN_KINDS: frozenset[str] = frozenset(
    {"agent_dispatched", "dispatch_attempt", "artifact_written"}
)


def _normalize_journal_line(line: dict[str, Any]) -> dict[str, Any]:
    """Normalize a journal line for golden comparison.

    P24 (code review): kind-based normalization — only `artifact_written` carries a
    real content hash that varies run-to-run. `agent_dispatched` + `dispatch_attempt`
    use a non-cryptographic sentinel and must be compared byte-exact. Previously a
    `_NULL_AFTER_HASH` magic-constant exception silently absorbed any all-zero hash
    regardless of kind, which would mask a future regression that produces an
    unexpected all-zero hash (e.g., a content-hash bug).
    """
    norm: dict[str, Any] = {**line}
    norm["monotonic_seq"] = "<SEQ>"
    norm["ts"] = "<TS>"
    if norm.get("kind") == "artifact_written" and norm.get("after_hash"):
        norm["after_hash"] = "sha256:<HASH>"
    payload = norm.get("payload")
    if isinstance(payload, dict):
        new_payload: dict[str, Any] = {**payload}
        if "idea_hash" in new_payload:
            new_payload["idea_hash"] = "sha256:<HASH>"
        if "topic_hash" in new_payload:
            new_payload["topic_hash"] = "sha256:<HASH>"
        if "run_id" in new_payload:
            new_payload["run_id"] = "<RUN_ID>"
        norm["payload"] = new_payload
    return norm


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Research journal uses POSIX append (Story 2A.3).",
)
def test_sdlc_research_happy_path_and_golden_journal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sdlc.cli import init as init_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(init_mod, "_get_repo_root_or_cwd", lambda: tmp_path)
    init_mod.run_init(ctx=None)

    with unittest.mock.patch("sdlc.cli.research._get_repo_root_or_cwd", return_value=tmp_path):
        result = _runner.invoke(app, ["research", "PCI compliance scope"])
    assert result.exit_code == 0, result.stderr + result.stdout

    art = tmp_path / "01-Requirement" / "02-Research" / "pci-compliance-scope.md"
    assert art.is_file()
    text = art.read_text(encoding="utf-8")
    assert "schema_version: 1" in text
    assert "kind: research" in text
    assert "topic: PCI compliance scope" in text or "topic:" in text

    runs_text = (tmp_path / "03-Implementation" / "agent_runs.jsonl").read_text(encoding="utf-8")
    prompts: list[str] = []
    for line in runs_text.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        dp = row.get("dispatch_prompt")
        if isinstance(dp, str):
            prompts.append(dp)
    assert any(BOUNDARY_LINE in p for p in prompts)
    assert any("PCI compliance scope" in p for p in prompts)

    golden_path = Path(__file__).parent / "fixtures" / "research" / "goldens" / "journal.jsonl"
    expected = [
        json.loads(line)
        for line in golden_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    actual: list[dict[str, Any]] = []
    for line in journal_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("kind") not in _RESEARCH_GOLDEN_KINDS:
            continue
        actual.append(_normalize_journal_line(entry))
    assert actual == expected


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_sdlc_research_rerun_dedup_preserves_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdlc.cli import init as init_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(init_mod, "_get_repo_root_or_cwd", lambda: tmp_path)
    init_mod.run_init(ctx=None)

    topic = "PCI compliance scope"
    with unittest.mock.patch("sdlc.cli.research._get_repo_root_or_cwd", return_value=tmp_path):
        r1 = _runner.invoke(app, ["research", topic])
    assert r1.exit_code == 0
    orig = tmp_path / "01-Requirement" / "02-Research" / "pci-compliance-scope.md"
    original_bytes = orig.read_bytes()

    with unittest.mock.patch("sdlc.cli.research._get_repo_root_or_cwd", return_value=tmp_path):
        r2 = _runner.invoke(app, ["research", topic])
    assert r2.exit_code == 0
    second = tmp_path / "01-Requirement" / "02-Research" / "pci-compliance-scope-2.md"
    assert second.is_file()
    assert orig.read_bytes() == original_bytes


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal")
def test_sdlc_research_phase_zero_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from sdlc.cli import init as init_mod
    from sdlc.state.model import State

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(init_mod, "_get_repo_root_or_cwd", lambda: tmp_path)
    init_mod.run_init(ctx=None)
    st = State(phase=0, next_monotonic_seq=0)
    (tmp_path / ".claude" / "state" / "state.json").write_text(
        json.dumps(st.model_dump(mode="json")), encoding="utf-8"
    )

    journal_before = (tmp_path / ".claude" / "state" / "journal.log").read_bytes()

    with unittest.mock.patch("sdlc.cli.research._get_repo_root_or_cwd", return_value=tmp_path):
        r = _runner.invoke(app, ["--json", "research", "topic"])
    assert r.exit_code == 1
    assert "ERR_PHASE_MISMATCH" in r.stderr
    assert (tmp_path / ".claude" / "state" / "journal.log").read_bytes() == journal_before
    assert not (tmp_path / "01-Requirement" / "02-Research").exists()
