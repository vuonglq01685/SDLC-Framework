"""Integration: `run_start` panel dispatch (Story 2A.8, Task 5)."""

from __future__ import annotations

import json
import unittest.mock
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sdlc.dispatcher.prompts import BOUNDARY_LINE

pytestmark = pytest.mark.integration


def test_run_start_panel_journal_and_product(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdlc.cli import init as init_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(init_mod, "_get_repo_root_or_cwd", lambda: tmp_path)
    init_mod.run_init(ctx=None)

    ctx = MagicMock()
    ctx.obj = {"json": False, "no_color": True}

    with unittest.mock.patch("sdlc.cli.start._get_repo_root_or_cwd", return_value=tmp_path):
        from sdlc.cli.start import run_start

        run_start(ctx=ctx, idea="Integration test idea", quiet=True)

    product = tmp_path / "01-Requirement" / "01-PRODUCT.md"
    assert product.is_file()
    text = product.read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "kind: product_brief" in text
    assert "## Product Brief" in text

    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    journal = journal_path.read_text(encoding="utf-8")
    assert journal.count('"kind":"agent_dispatched"') == 4
    assert journal.count('"kind":"dispatch_attempt"') >= 4
    assert journal.count('"kind":"artifact_written"') >= 1

    # P38 + P39 (Story 2A.8): assert hash sentinels + temporal specialist ordering
    # on agent_dispatched entries. AC4 + Task 5.2 mandate the hash-pattern check;
    # ordering verifies primary → parallel pair → synthesizer pipeline shape.
    journal_entries = [json.loads(line) for line in journal.splitlines() if line.strip()]
    journal_entries.sort(key=lambda e: e["monotonic_seq"])
    dispatched_entries = [e for e in journal_entries if e["kind"] == "agent_dispatched"]
    assert len(dispatched_entries) == 4

    _NULL_HASH_SENTINEL = "sha256:" + "0" * 64
    expected_specialists = {
        "product-strategist",
        "technical-researcher",
        "devil-advocate",
        "requirement-synthesizer",
    }
    seen_specialists = set()
    for entry in dispatched_entries:
        payload = entry["payload"]
        seen_specialists.add(payload["specialist"])
        # P38: EPIC-2A-DEBT-JOURNAL-NULL-AFTER-HASH sentinel pattern
        assert entry["before_hash"] is None
        assert entry["after_hash"] == _NULL_HASH_SENTINEL
    assert seen_specialists == expected_specialists

    # P39: ordering — primary first, synthesizer last, parallel pair between
    dispatched_names = [e["payload"]["specialist"] for e in dispatched_entries]
    assert dispatched_names[0] == "product-strategist"
    assert dispatched_names[-1] == "requirement-synthesizer"
    middle = set(dispatched_names[1:-1])
    assert middle == {"technical-researcher", "devil-advocate"}

    runs_path = tmp_path / "03-Implementation" / "agent_runs.jsonl"
    assert runs_path.is_file()
    runs_text = runs_path.read_text(encoding="utf-8")
    for line in runs_text.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("dispatch_prompt"):
            # P60: BOUNDARY_LINE appears EXACTLY ONCE, inside a single
            # <BOUNDARY>...</BOUNDARY> block (Story 2A.8 prompt hardening).
            assert row["dispatch_prompt"].count(BOUNDARY_LINE) == 1
            assert row["dispatch_prompt"].count("<BOUNDARY>") == 1

    # Story 2A.8 D2-B: synthesizer is the canonical writer; artifact_written's
    # actor is the agent name (not 'cli').
    assert '"actor":"agent:requirement-synthesizer"' in journal

    state = json.loads((tmp_path / ".claude" / "state" / "state.json").read_text(encoding="utf-8"))
    assert state.get("phase") == 1
