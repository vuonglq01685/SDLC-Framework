"""Cross-process determinism integration test for engine.scanner.scan (Story 1.15)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_SCAN_SCRIPT = """\
import json, sys
from pathlib import Path
from sdlc.engine import scan
root = Path(sys.argv[1])
state = scan(root)
payload = state.model_dump(mode="json")
print(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
"""


def _build_corpus(root: Path) -> None:
    epic_d = root / "01-Requirement" / "04-Epics"
    epic_d.mkdir(parents=True)
    for slug in ("alpha", "bravo", "charlie"):
        (epic_d / f"EPIC-{slug}.json").write_text(
            json.dumps({"id": f"EPIC-{slug}", "title": slug}), encoding="utf-8"
        )
    story_d = root / "01-Requirement" / "05-Stories" / "EPIC-alpha"
    story_d.mkdir(parents=True)
    (story_d / "EPIC-alpha-S01-boot.json").write_text(
        json.dumps({"id": "EPIC-alpha-S01-boot"}), encoding="utf-8"
    )
    task_d = root / "03-Implementation" / "tasks" / "EPIC-alpha-S01-boot"
    task_d.mkdir(parents=True)
    (task_d / "EPIC-alpha-S01-boot-T01-init.json").write_text(
        json.dumps({"id": "EPIC-alpha-S01-boot-T01-init"}), encoding="utf-8"
    )


@pytest.mark.skipif(
    sys.platform == "win32" and shutil.which("uv") is None,
    reason="cross-process test requires uv on PATH; skip on Windows if absent",
)
def test_scan_idempotent_across_processes(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    _build_corpus(corpus)

    # Anchor `uv run` to the project root so the test is hermetic regardless
    # of the directory pytest is invoked from (Story 1.15 review patch).
    project_root = Path(__file__).resolve().parents[2]

    def _run() -> str:
        result = subprocess.run(
            ["uv", "run", "python", "-c", _SCAN_SCRIPT, str(corpus)],
            capture_output=True,
            text=True,
            check=True,
            cwd=project_root,
        )
        return result.stdout.strip()

    out1 = _run()
    out2 = _run()
    assert out1 == out2, (
        f"scan() produced different output across two process invocations:\n{out1}\nvs\n{out2}"
    )
