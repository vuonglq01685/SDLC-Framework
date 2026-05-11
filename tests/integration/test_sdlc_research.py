"""Integration tests for ``sdlc research`` (Story 2A.9, Task 5)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from typer.testing import CliRunner

from sdlc.cli.main import app
from sdlc.dispatcher.prompts import BOUNDARY_LINE

pytestmark = pytest.mark.integration

_runner = CliRunner()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal append")
def test_research_writes_artifact_and_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdlc.cli import init as init_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(init_mod, "_get_repo_root_or_cwd", lambda: tmp_path)
    init_mod.run_init(ctx=None)

    topic = "PCI compliance scope"
    with patch("sdlc.cli.research._get_repo_root_or_cwd", return_value=tmp_path):
        r = _runner.invoke(app, ["research", topic])
    assert r.exit_code == 0, r.stderr + r.stdout

    art = tmp_path / "01-Requirement" / "02-Research" / "pci-compliance-scope.md"
    assert art.is_file()
    text = art.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    front = yaml.safe_load(parts[1])
    assert front["kind"] == "research"
    assert front["topic"] == topic
    assert front["slug"] == "pci-compliance-scope"
    assert front["researched_by_specialist"] == "technical-researcher"
    body = parts[2]
    # P5 (code review): direct H2 presence assertion replaces tautological
    # "not in body or in body" combinator that was satisfied by any non-PCI body.
    assert "## Research Findings" in body

    runs = (tmp_path / "03-Implementation" / "agent_runs.jsonl").read_text(encoding="utf-8")
    prompts = [json.loads(line)["dispatch_prompt"] for line in runs.splitlines() if line.strip()]
    assert any(BOUNDARY_LINE in p for p in prompts if isinstance(p, str))
    assert any(topic in p for p in prompts if isinstance(p, str))

    # P6 (code review): exactly-one assertions match AC6/D2 (suppress dispatcher's
    # internal artifact_written; only the CLI re-write emits one).
    entries: list[dict[str, object]] = []
    for line in (
        (tmp_path / ".claude" / "state" / "journal.log").read_text(encoding="utf-8").splitlines()
    ):
        if line.strip():
            entries.append(json.loads(line))
    kinds = [e["kind"] for e in entries]
    assert kinds.count("agent_dispatched") == 1
    assert kinds.count("artifact_written") == 1

    # P11 (code review): hash equality against the FINAL (frontmatter-prepended)
    # on-disk bytes — AC6/D2 invariant: CLI's re-write emits a single
    # artifact_written whose after_hash covers the wrapped artifact, not the raw
    # specialist body.
    import hashlib

    aw = next(e for e in entries if e["kind"] == "artifact_written")
    assert aw["before_hash"] is None
    expected = "sha256:" + hashlib.sha256(art.read_bytes()).hexdigest()
    assert aw["after_hash"] == expected
