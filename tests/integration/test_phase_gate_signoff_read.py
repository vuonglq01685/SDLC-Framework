"""Integration tests for phase_gate signoff read logic (AC5, Story 2A.4 Task 8.2)."""

from __future__ import annotations

import pytest

from sdlc.contracts.hook_payload import HookPayload
from sdlc.hooks.builtin.phase_gate import phase_gate


def _p(path: str) -> HookPayload:
    return HookPayload(
        hook_name="phase_gate",
        target_path=path,
        target_kind="write_intent",
        content_hash_before=None,
        write_intent="test write",
    )


def _write_signoff(tmp_path, phase: int, content: str) -> None:
    signoff_dir = tmp_path / ".claude" / "state" / "signoffs"
    signoff_dir.mkdir(parents=True, exist_ok=True)
    (signoff_dir / f"phase-{phase}.yaml").write_text(content)


@pytest.mark.integration
class TestPhaseGateSignoffRead:
    def test_phase1_approved_true_allows_phase2(self, tmp_path) -> None:
        _write_signoff(tmp_path, phase=1, content="approved: true\nphase: 1\n")
        result = phase_gate(_p("02-Architecture/01-UX/01-tokens.md"), repo_root=tmp_path)
        assert result.decision == "allow"

    def test_phase1_approved_false_denies_phase2(self, tmp_path) -> None:
        _write_signoff(tmp_path, phase=1, content="approved: false\nphase: 1\n")
        result = phase_gate(_p("02-Architecture/01-UX/01-tokens.md"), repo_root=tmp_path)
        assert result.decision == "deny"
        assert "approved=false" in (result.reason or "")

    def test_phase1_absent_denies_phase2(self, tmp_path) -> None:
        result = phase_gate(_p("02-Architecture/01-UX/01-tokens.md"), repo_root=tmp_path)
        assert result.decision == "deny"
        assert "not found" in (result.reason or "")

    def test_corrupted_yaml_denies(self, tmp_path) -> None:
        """Corrupted YAML in signoff file → deny with 'corrupted' in reason."""
        _write_signoff(tmp_path, phase=1, content="{ invalid yaml: [unclosed")
        result = phase_gate(_p("02-Architecture/01-UX/01-tokens.md"), repo_root=tmp_path)
        assert result.decision == "deny"
        assert "corrupted" in (result.reason or "")

    def test_phase2_approved_true_allows_phase3(self, tmp_path) -> None:
        _write_signoff(tmp_path, phase=2, content="approved: true\nphase: 2\n")
        result = phase_gate(_p("03-Implementation/01-API/server.py"), repo_root=tmp_path)
        assert result.decision == "allow"

    def test_phase2_absent_denies_phase3(self, tmp_path) -> None:
        result = phase_gate(_p("03-Implementation/01-API/server.py"), repo_root=tmp_path)
        assert result.decision == "deny"
        assert "phase-2.yaml" in (result.reason or "")
