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
    runs_lines = runs_path.read_text(encoding="utf-8").splitlines()
    # JSONL is written with ensure_ascii=True (`telemetry/runs.py`), so the em
    # dash inside BOUNDARY_LINE is encoded as `\u2014`. Compare against the
    # unescaped `dispatch_prompt` field per row.
    boundary_seen = False
    for raw in runs_lines:
        if not raw.strip():
            continue
        row = json.loads(raw)
        if BOUNDARY_LINE in row.get("dispatch_prompt", ""):
            boundary_seen = True
            break
    assert boundary_seen, "expected BOUNDARY_LINE to appear in dispatch_prompt"


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


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Verify journal uses POSIX append (Story 2A.3); Windows skipped like start e2e.",
)
def test_sdlc_verify_failed_verdict_exits_nonzero_with_failed_row(tmp_path: Path) -> None:
    """P30 / P31 / DC10=(a) (post-review 2026-05-12 Cluster C-J): when the
    verifier returns ``{"verdict": "failed", "note": "..."}`` the ceremony
    MUST:

      * still persist a `verifications:` row with ``status: "failed"``
        and the verifier's note,
      * still emit the journal `artifact_verified` event with
        ``payload.status == "failed"``,
      * EXIT NON-ZERO so CI / scripts observe the verifier's verdict.

    Dispatcher outcome remains "success" — only the verifier's PARSED
    VERDICT was non-verified. This pins the AC2 dual-signal amendment.
    """
    from sdlc.cli._verify_mock import set_mock_verdict_override

    artifact_body = (
        "---\n"
        "schema_version: 1\n"
        "kind: product_brief\n"
        "title: Failing PRD\n"
        "---\n"
        "# Failing PRD\n\nBody that fails verification.\n"
    )
    artifact = _initialise(tmp_path, artifact_body=artifact_body)

    set_mock_verdict_override({"verdict": "failed", "note": "missing acceptance criteria; reject"})
    try:
        with unittest.mock.patch("sdlc.cli.verify._get_repo_root_or_cwd", return_value=tmp_path):
            result = _runner.invoke(app, ["verify", "01-Requirement/01-PRODUCT.md"])
    finally:
        set_mock_verdict_override(None)  # always clear

    # P30: exit non-zero even though dispatcher outcome was success.
    assert result.exit_code != 0, result.stderr + result.stdout
    combined = (result.stderr or "") + (result.stdout or "")
    # Must NOT route through ERR_PANEL_DISPATCH_FAILED (dispatcher outcome OK).
    assert "ERR_PANEL_DISPATCH_FAILED" not in combined, combined

    from sdlc.cli.verify import _parse_frontmatter

    frontmatter, _body = _parse_frontmatter(artifact.read_text(encoding="utf-8"))
    verifications = frontmatter["verifications"]
    assert isinstance(verifications, list) and len(verifications) == 1
    entry = verifications[0]
    assert entry["status"] == "failed"
    assert entry["verifier_note"] == "missing acceptance criteria; reject"

    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    journal_entries = [
        json.loads(line)
        for line in journal_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    verified_rows = [e for e in journal_entries if e["kind"] == "artifact_verified"]
    assert len(verified_rows) == 1
    assert verified_rows[0]["payload"]["status"] == "failed"


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Verify journal uses POSIX append (Story 2A.3); Windows skipped like start e2e.",
)
def test_sdlc_verify_journal_pins_all_four_hashes(tmp_path: Path) -> None:
    """P29 / DC8=(2) (post-review 2026-05-12 Cluster C-J): regression pin for
    the four hashes the verify ceremony exposes — distinct semantics:

      1. `agent_dispatched.payload.idea_hash` — sha256 of idea_text bytes
         (legacy; preserved per DC8=(2) backward-compat).
      2. `agent_dispatched.payload.artifact_hash_at_dispatch` — sha256 of
         whole-file bytes at dispatch time (P29 new key; ALONGSIDE the
         legacy idea_hash, NOT a rename).
      3. `artifact_verified.before_hash` (top-level) — sha256 of whole-file
         bytes BEFORE the frontmatter rewrite (= artifact_hash_at_dispatch
         when the TOCTOU race-check holds).
      4. `artifact_verified.after_hash` (top-level) — sha256 of whole-file
         bytes AFTER the frontmatter rewrite (differs from before_hash by
         exactly the appended `verifications:` block).
      Plus: `artifact_verified.payload.content_hash_at_verify` (body-only;
      drives 2A.12 drift detection — semantics UNCHANGED).
    """
    artifact_body = (
        "---\n"
        "schema_version: 1\n"
        "kind: product_brief\n"
        "title: Hash Audit PRD\n"
        "---\n"
        "# Hash Audit\n\nBody for hash invariants.\n"
    )
    _initialise(tmp_path, artifact_body=artifact_body)

    with unittest.mock.patch("sdlc.cli.verify._get_repo_root_or_cwd", return_value=tmp_path):
        result = _runner.invoke(app, ["verify", "01-Requirement/01-PRODUCT.md"])
    assert result.exit_code == 0, result.stderr + result.stdout

    journal_path = tmp_path / ".claude" / "state" / "journal.log"
    entries = [
        json.loads(line)
        for line in journal_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    dispatched = next(e for e in entries if e["kind"] == "agent_dispatched")
    verified = next(e for e in entries if e["kind"] == "artifact_verified")

    # (1) Legacy idea_hash preserved (DC8=(2) backward-compat).
    assert dispatched["payload"]["idea_hash"].startswith("sha256:")
    assert len(dispatched["payload"]["idea_hash"]) == len("sha256:") + 64

    # (2) New artifact_hash_at_dispatch key (whole-file pre-dispatch). For
    # `/sdlc-verify` ``idea_text == artifact_content`` so the two hashes
    # coincide on this dispatch path; they remain SEMANTICALLY distinct
    # (idea_hash is over idea_text; artifact_hash_at_dispatch is over the
    # on-disk file). Future dispatch paths where idea_text differs from
    # the on-disk artifact would see them diverge.
    artifact_hash_at_dispatch = dispatched["payload"]["artifact_hash_at_dispatch"]
    assert artifact_hash_at_dispatch.startswith("sha256:")
    assert len(artifact_hash_at_dispatch) == len("sha256:") + 64

    # (3) artifact_verified.before_hash == artifact_hash_at_dispatch (TOCTOU
    # check holds; same whole-file bytes at both points).
    assert verified["before_hash"] == artifact_hash_at_dispatch

    # (4) after_hash differs (frontmatter grew by the verifications: block).
    assert verified["after_hash"].startswith("sha256:")
    assert verified["after_hash"] != verified["before_hash"]

    # body-only content_hash_at_verify unchanged semantics (drives drift detection).
    content_hash = verified["payload"]["content_hash_at_verify"]
    assert content_hash.startswith("sha256:") and len(content_hash) == len("sha256:") + 64
    # body-only hash differs from whole-file hash (frontmatter contributes bytes).
    assert content_hash != verified["before_hash"]
