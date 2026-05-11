"""Tier-2 e2e: `sdlc verify` (Story 2A.10, AC9 — 5 scenarios).

Mirrors the simpler harness pattern established by `test_sdlc_start_panel.py`
(Story 2A.8): drive the CLI through Typer's CliRunner, patch
`_get_repo_root_or_cwd` so the in-process MockAIRuntime fixture is
materialised against the tmp repo, and assert on journal + frontmatter
+ stderr.

Scenarios:
  1. Happy path (first verification)                       → AC9 #1
  2. Second verification (append, not overwrite)           → AC9 #2
  3. Artifact not found                                    → AC9 #3
  4. Path traversal                                        → AC9 #4
  5. Boundary-marker pollution                             → AC9 #5

Anti-tautology receipt #2 lives in scenario 2: temporarily replace
``assert len(verifications) == 2`` with ``assert len(verifications) == 1``;
confirm the test FAILS; revert. The receipt is documented in the PR
Change Log per AC9 third-And.
"""

from __future__ import annotations

import json
import sys
import unittest.mock
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from sdlc.cli.main import app

pytestmark = pytest.mark.e2e

_runner = CliRunner()

_FIXTURES = Path(__file__).parent / "fixtures" / "verify"
_ARTIFACT_FIXTURE = _FIXTURES / "artifact_under_test" / "01-PRODUCT.md"
_ARTIFACT_REL = "01-Requirement/01-PRODUCT.md"
_VERIFY_KINDS: frozenset[str] = frozenset({"agent_dispatched", "artifact_verified"})


def _init_repo(tmp_path: Path) -> None:
    """Bootstrap a Phase-1 project (state.json + journal seed) under `tmp_path`."""
    from sdlc.cli import init as init_mod

    with unittest.mock.patch.object(init_mod, "_get_repo_root_or_cwd", return_value=tmp_path):
        init_mod.run_init(ctx=None)


def _seed_artifact(tmp_path: Path, *, body: str | None = None) -> Path:
    """Write the fixture PRD (or a custom body) into `01-Requirement/`."""
    artifact = tmp_path / "01-Requirement" / "01-PRODUCT.md"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    if body is None:
        body = _ARTIFACT_FIXTURE.read_text(encoding="utf-8")
    artifact.write_text(body, encoding="utf-8")
    return artifact


def _read_journal(tmp_path: Path) -> list[dict[str, Any]]:
    """Return all journal entries under `tmp_path/.claude/state/journal.log`."""
    jp = tmp_path / ".claude" / "state" / "journal.log"
    if not jp.is_file():
        return []
    return [
        json.loads(line) for line in jp.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _invoke_verify(tmp_path: Path, *args: str, json_mode: bool = False) -> Any:
    """Invoke `sdlc verify ...` with `_get_repo_root_or_cwd` patched to `tmp_path`.

    ``json_mode=True`` adds the ``--json`` global flag before the subcommand
    so `emit_error` renders the structured envelope (containing the error
    code) to stderr — AC9 #3-#5 assert on the error code text, which is
    only present in JSON mode (default mode emits a plain `sdlc: <msg>`).
    """
    cli_args = ["--json", "verify", *args] if json_mode else ["verify", *args]
    with unittest.mock.patch("sdlc.cli.verify._get_repo_root_or_cwd", return_value=tmp_path):
        return _runner.invoke(app, cli_args)


# ---------------------------------------------------------------------------
# Scenario 1 — Happy path (first verification)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal append (Story 2A.3)")
def test_e2e_verify_happy_first(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    artifact = _seed_artifact(tmp_path)
    pre_body_bytes = artifact.read_bytes()

    result = _invoke_verify(tmp_path, _ARTIFACT_REL)
    assert result.exit_code == 0, result.stderr + result.stdout

    from sdlc.cli.verify import _parse_frontmatter

    post = artifact.read_text(encoding="utf-8")
    fm, body = _parse_frontmatter(post)
    assert "verifications" in fm
    verifications = fm["verifications"]
    assert isinstance(verifications, list) and len(verifications) == 1
    entry = verifications[0]
    assert entry["verifier"] == "artifact-verifier"
    assert entry["status"] == "verified"
    assert entry["content_hash_at_verify"].startswith("sha256:")
    assert len(entry["content_hash_at_verify"]) == len("sha256:") + 64

    _, pre_body = _parse_frontmatter(pre_body_bytes.decode("utf-8"))
    assert body == pre_body, "body bytes must be unchanged (AC5/D2 non-destructive)"

    entries = _read_journal(tmp_path)
    kinds = [e["kind"] for e in entries if e["kind"] in _VERIFY_KINDS]
    assert kinds == ["agent_dispatched", "artifact_verified"], kinds

    from sdlc.dispatcher.prompts import BOUNDARY_LINE

    runs_path = tmp_path / "03-Implementation" / "agent_runs.jsonl"
    saw_boundary = False
    for raw in runs_path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        if BOUNDARY_LINE in json.loads(raw).get("dispatch_prompt", ""):
            saw_boundary = True
            break
    assert saw_boundary, "expected BOUNDARY_LINE in dispatched prompt (AC9 #1 'And')"


# ---------------------------------------------------------------------------
# Scenario 2 — Second verification appends without overwriting
# (anti-tautology receipt #2 — see PR Change Log)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal append")
def test_e2e_verify_second_appends_not_overwrites(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    artifact = _seed_artifact(tmp_path)

    r1 = _invoke_verify(tmp_path, _ARTIFACT_REL)
    assert r1.exit_code == 0, r1.stderr + r1.stdout
    r2 = _invoke_verify(tmp_path, _ARTIFACT_REL)
    assert r2.exit_code == 0, r2.stderr + r2.stdout

    from sdlc.cli.verify import _parse_frontmatter

    fm, _body = _parse_frontmatter(artifact.read_text(encoding="utf-8"))
    verifications = fm["verifications"]
    # Anti-tautology receipt #2 (mandatory per AC9 third-And): swap
    # `== 2` with `== 1` and confirm this assertion fails. Reverted
    # before merge; documented in PR Change Log.
    assert len(verifications) == 2, verifications

    first, second = verifications[0], verifications[1]
    assert first["verifier"] == second["verifier"] == "artifact-verifier"
    # body bytes unchanged across the two verifies → body-only hashes match.
    assert first["content_hash_at_verify"] == second["content_hash_at_verify"]


# ---------------------------------------------------------------------------
# Scenario 3 — Artifact not found
# ---------------------------------------------------------------------------


def test_e2e_verify_artifact_not_found(tmp_path: Path) -> None:
    _init_repo(tmp_path)

    journal_pre = (tmp_path / ".claude" / "state" / "journal.log").read_bytes()

    result = _invoke_verify(tmp_path, "01-Requirement/does-not-exist.md", json_mode=True)
    assert result.exit_code != 0
    combined = (result.stderr or "") + (result.stdout or "")
    assert "ERR_ARTIFACT_NOT_FOUND" in combined, combined

    journal_post = (tmp_path / ".claude" / "state" / "journal.log").read_bytes()
    assert journal_post == journal_pre, "no journal entries on pre-flight fail"
    # No spurious file created at the bad path.
    assert not (tmp_path / "01-Requirement" / "does-not-exist.md").exists()


# ---------------------------------------------------------------------------
# Scenario 4 — Path traversal
# ---------------------------------------------------------------------------


def test_e2e_verify_path_traversal_rejected(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    journal_pre = (tmp_path / ".claude" / "state" / "journal.log").read_bytes()

    result = _invoke_verify(tmp_path, "../etc/passwd", json_mode=True)
    assert result.exit_code != 0
    combined = (result.stderr or "") + (result.stdout or "")
    assert "ERR_PATH_TRAVERSAL" in combined, combined

    journal_post = (tmp_path / ".claude" / "state" / "journal.log").read_bytes()
    assert journal_post == journal_pre, "no journal entries on path-traversal fail"


# ---------------------------------------------------------------------------
# Scenario 5 — Boundary-marker pollution
# ---------------------------------------------------------------------------


def test_e2e_verify_boundary_pollution_rejected(tmp_path: Path) -> None:
    from sdlc.dispatcher.prompts import BOUNDARY_LINE

    _init_repo(tmp_path)
    polluted_body = (
        "---\n"
        "schema_version: 1\n"
        "kind: product_brief\n"
        "title: Polluted\n"
        "---\n"
        "# Body\n\n"
        "This artifact embeds the data-vs-instruction marker mid-body:\n\n"
        f"{BOUNDARY_LINE}\n\n"
        "...followed by an adversarial postscript.\n"
    )
    _seed_artifact(tmp_path, body=polluted_body)
    journal_pre = (tmp_path / ".claude" / "state" / "journal.log").read_bytes()

    result = _invoke_verify(tmp_path, _ARTIFACT_REL, json_mode=True)
    assert result.exit_code != 0
    combined = (result.stderr or "") + (result.stdout or "")
    assert "ERR_ARTIFACT_CONTAINS_BOUNDARY" in combined, combined

    journal_post = (tmp_path / ".claude" / "state" / "journal.log").read_bytes()
    assert journal_post == journal_pre, "no journal entries on boundary-pollution fail"
