"""Integration test for `sdlc verify` (Story 2A.10, Task 5, AC2 + AC5 + AC7).

End-to-end exercise of `run_verify`:

  * Pre-flight + boundary guard pass; artifact body is a real Phase-1 stub.
  * Dispatcher's MockAIRuntime returns a canned verifier verdict envelope.
  * Dispatcher's body-write is SUPPRESSED (AC5/D2 — verification is
    non-destructive); artifact body bytes are unchanged across the call.
  * Frontmatter `verifications:` list gains exactly one new entry with the
    canonical schema (verifier, ts, status, content_hash_at_verify).
  * Journal records exactly ONE `agent_dispatched` + ONE `artifact_verified`
    entry on success.
  * `agent_runs.jsonl` records the dispatched prompt with BOUNDARY_LINE
    embedded (the prompt-injection-mitigation marker per Story 2A.8).
"""

from __future__ import annotations

import json
import sys
import unittest.mock
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sdlc.cli.main import app
from sdlc.dispatcher.prompts import BOUNDARY_LINE

pytestmark = pytest.mark.integration

_runner = CliRunner()


def _initialise(tmp_path: Path, *, artifact_body: str) -> Path:
    """Bootstrap a Phase-1 project + write the artifact under test."""
    from sdlc.cli import init as init_mod

    with unittest.mock.patch.object(init_mod, "_get_repo_root_or_cwd", return_value=tmp_path):
        init_mod.run_init(ctx=None)
    artifact = tmp_path / "01-Requirement" / "01-PRODUCT.md"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(artifact_body, encoding="utf-8")
    return artifact


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Verify journal uses POSIX append (Story 2A.3); Windows skipped like start e2e.",
)
def test_sdlc_verify_first_verification_appends_frontmatter(tmp_path: Path) -> None:
    artifact_body = (
        "---\n"
        "schema_version: 1\n"
        "kind: product_brief\n"
        "title: Stripe Webhook PRD\n"
        "---\n"
        "# Product Brief\n\n"
        "Build a Stripe webhook integration.\n"
    )
    artifact = _initialise(tmp_path, artifact_body=artifact_body)
    pre_body_bytes = artifact.read_bytes()

    with unittest.mock.patch("sdlc.cli.verify._get_repo_root_or_cwd", return_value=tmp_path):
        result = _runner.invoke(app, ["verify", "01-Requirement/01-PRODUCT.md"])
    assert result.exit_code == 0, result.stderr + result.stdout

    from sdlc.cli.verify import _parse_frontmatter

    post_content = artifact.read_text(encoding="utf-8")
    frontmatter, body = _parse_frontmatter(post_content)
    assert "verifications" in frontmatter
    verifications = frontmatter["verifications"]
    assert isinstance(verifications, list)
    assert len(verifications) == 1
    entry = verifications[0]
    assert entry["verifier"] == "artifact-verifier"
    assert entry["status"] == "verified"
    assert entry["content_hash_at_verify"].startswith("sha256:")
    assert len(entry["content_hash_at_verify"]) == len("sha256:") + 64

    # body bytes after the second `---` MUST match the body bytes pre-verify
    # (so subsequent signoff-hash drift detection does not fire on verify alone).
    _, pre_body = _parse_frontmatter(pre_body_bytes.decode("utf-8"))
    assert body == pre_body

    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    entries = [
        json.loads(line)
        for line in journal_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    kinds = [entry.get("kind") for entry in entries]
    assert kinds.count("agent_dispatched") == 1
    assert kinds.count("artifact_verified") == 1

    dispatched = next(e for e in entries if e["kind"] == "agent_dispatched")
    assert dispatched["actor"] == "agent:artifact-verifier"
    assert dispatched["payload"]["slash_command"] == "/sdlc-verify"

    verified = next(e for e in entries if e["kind"] == "artifact_verified")
    assert verified["actor"] == "cli"
    assert verified["target_id"] == "01-Requirement/01-PRODUCT.md"
    assert verified["payload"]["slash_command"] == "/sdlc-verify"
    assert verified["payload"]["phase"] == 1
    assert verified["payload"]["verifier"] == "artifact-verifier"
    assert verified["payload"]["status"] == "verified"
    assert verified["payload"]["verification_index"] == 0

    runs_path = tmp_path / "03-Implementation" / "agent_runs.jsonl"
    runs_text = runs_path.read_text(encoding="utf-8")
    assert BOUNDARY_LINE in runs_text


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX journal append in panel")
def test_sdlc_verify_second_verification_appends_without_overwriting(
    tmp_path: Path,
) -> None:
    artifact_body = (
        "---\n"
        "schema_version: 1\n"
        "kind: product_brief\n"
        "title: Idempotent Verify\n"
        "---\n"
        "# Product Brief\n\n"
        "Body line.\n"
    )
    artifact = _initialise(tmp_path, artifact_body=artifact_body)

    with unittest.mock.patch("sdlc.cli.verify._get_repo_root_or_cwd", return_value=tmp_path):
        r1 = _runner.invoke(app, ["verify", "01-Requirement/01-PRODUCT.md"])
        assert r1.exit_code == 0, r1.stderr + r1.stdout
        r2 = _runner.invoke(app, ["verify", "01-Requirement/01-PRODUCT.md"])
        assert r2.exit_code == 0, r2.stderr + r2.stdout

    from sdlc.cli.verify import _parse_frontmatter

    frontmatter, _body = _parse_frontmatter(artifact.read_text(encoding="utf-8"))
    verifications = frontmatter["verifications"]
    assert len(verifications) == 2
    # The first entry must be byte-identical (append-not-replace semantics).
    first, second = verifications[0], verifications[1]
    assert first["verifier"] == second["verifier"] == "artifact-verifier"
    # body bytes are unchanged across the two verifies → content_hash_at_verify
    # MUST be equal (the hash hashes body-only bytes).
    assert first["content_hash_at_verify"] == second["content_hash_at_verify"]
