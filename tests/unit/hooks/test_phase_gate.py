"""Tests for hooks/builtin/phase_gate.py (AC5, Story 2A.4 Task 4)."""

from __future__ import annotations

import pytest
import yaml

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


def _write_signoff(tmp_path, phase: int, approved: bool) -> None:
    signoff_dir = tmp_path / ".claude" / "state" / "signoffs"
    signoff_dir.mkdir(parents=True, exist_ok=True)
    signoff_file = signoff_dir / f"phase-{phase}.yaml"
    signoff_file.write_text(yaml.dump({"approved": approved, "phase": phase}))


@pytest.mark.unit
class TestPhaseGatePhase1:
    def test_phase1_path_always_allows(self, tmp_path) -> None:
        result = phase_gate(_p("01-Requirement/04-Epics/EPIC-foo.json"), repo_root=tmp_path)
        assert result.decision == "allow"

    def test_phase1_path_no_signoff_file_allows(self, tmp_path) -> None:
        result = phase_gate(_p("01-Requirement/01-PRODUCT.md"), repo_root=tmp_path)
        assert result.decision == "allow"


@pytest.mark.unit
class TestPhaseGatePhase2:
    def test_phase2_no_signoff_denies(self, tmp_path) -> None:
        result = phase_gate(_p("02-Architecture/01-UX/01-tokens.md"), repo_root=tmp_path)
        assert result.decision == "deny"
        assert result.error_code == "phase_gate_violation"
        assert "phase-1.yaml" in (result.reason or "")

    def test_phase2_approved_false_denies(self, tmp_path) -> None:
        """Task 4.4 anti-tautology: approved=false must deny."""
        _write_signoff(tmp_path, phase=1, approved=False)
        result = phase_gate(_p("02-Architecture/01-UX/01-tokens.md"), repo_root=tmp_path)
        assert result.decision == "deny"
        assert result.error_code == "phase_gate_violation"
        assert "approved=false" in (result.reason or "")

    def test_phase2_approved_true_allows(self, tmp_path) -> None:
        _write_signoff(tmp_path, phase=1, approved=True)
        result = phase_gate(_p("02-Architecture/01-UX/01-tokens.md"), repo_root=tmp_path)
        assert result.decision == "allow"


@pytest.mark.unit
class TestPhaseGatePhase3:
    def test_phase3_no_signoff_denies(self, tmp_path) -> None:
        result = phase_gate(_p("03-Implementation/01-API/server.py"), repo_root=tmp_path)
        assert result.decision == "deny"
        assert result.error_code == "phase_gate_violation"
        assert "phase-2.yaml" in (result.reason or "")

    def test_phase3_approved_false_denies(self, tmp_path) -> None:
        _write_signoff(tmp_path, phase=2, approved=False)
        result = phase_gate(_p("03-Implementation/01-API/server.py"), repo_root=tmp_path)
        assert result.decision == "deny"

    def test_phase3_approved_true_allows(self, tmp_path) -> None:
        _write_signoff(tmp_path, phase=2, approved=True)
        result = phase_gate(_p("03-Implementation/01-API/server.py"), repo_root=tmp_path)
        assert result.decision == "allow"


@pytest.mark.unit
class TestPhaseGateNonPhasePaths:
    def test_claude_state_path_allows(self, tmp_path) -> None:
        result = phase_gate(_p(".claude/state/signoffs/phase-1.yaml"), repo_root=tmp_path)
        assert result.decision == "allow"

    def test_bmad_output_path_allows(self, tmp_path) -> None:
        result = phase_gate(_p("_bmad-output/planning-artifacts/prd.md"), repo_root=tmp_path)
        assert result.decision == "allow"

    def test_tests_path_allows(self, tmp_path) -> None:
        result = phase_gate(_p("tests/unit/test_foo.py"), repo_root=tmp_path)
        assert result.decision == "allow"

    def test_pyproject_toml_allows(self, tmp_path) -> None:
        result = phase_gate(_p("pyproject.toml"), repo_root=tmp_path)
        assert result.decision == "allow"

    def test_signoff_record_write_allows(self, tmp_path) -> None:
        """Writing the signoff record itself (under .claude/) MUST be allowed (AC5 explicit)."""
        result = phase_gate(_p(".claude/state/signoffs/phase-2.yaml"), repo_root=tmp_path)
        assert result.decision == "allow"


@pytest.mark.unit
class TestPhaseGateWindowsPath:
    def test_windows_separator_still_gated(self, tmp_path) -> None:
        """PurePosixPath on Windows backslash paths: leading component still starts with '02-'."""
        result = phase_gate(_p("02-Architecture\\01-UX\\01-tokens.md"), repo_root=tmp_path)
        # PurePosixPath treats backslash as a literal character, so
        # parts[0] == "02-Architecture\\01-UX\\01-tokens.md" — which still starts
        # with "02-". The gate therefore fires (conservatively correct: deny).
        # Dispatcher is expected to normalise paths to POSIX before calling hooks,
        # but even if it doesn't, the hook remains safe.
        assert result.decision == "deny"

    def test_posix_path_properly_gated(self, tmp_path) -> None:
        """Standard POSIX path is correctly gated."""
        result = phase_gate(_p("02-Architecture/01-UX/01-tokens.md"), repo_root=tmp_path)
        assert result.decision == "deny"


@pytest.mark.unit
class TestPhaseGateEdgeCases:
    def test_empty_target_path_allows(self, tmp_path) -> None:
        """Empty string path → _get_leading_dir returns None → allow (line 48 coverage)."""
        result = phase_gate(_p(""), repo_root=tmp_path)
        assert result.decision == "allow"

    def test_non_dict_yaml_in_signoff_denies(self, tmp_path) -> None:
        """Signoff file exists but YAML is a plain string, not a dict → deny (lines 59 coverage)."""
        signoff_dir = tmp_path / ".claude" / "state" / "signoffs"
        signoff_dir.mkdir(parents=True, exist_ok=True)
        (signoff_dir / "phase-1.yaml").write_text("just a string\n", encoding="utf-8")
        result = phase_gate(_p("02-Architecture/01-UX/01-tokens.md"), repo_root=tmp_path)
        assert result.decision == "deny"
        assert result.error_code == "phase_gate_violation"

    def test_corrupted_yaml_signoff_denies(self, tmp_path) -> None:
        """Signoff file exists with broken YAML → YAMLError caught → deny (lines 61-63, 70-71)."""
        signoff_dir = tmp_path / ".claude" / "state" / "signoffs"
        signoff_dir.mkdir(parents=True, exist_ok=True)
        (signoff_dir / "phase-1.yaml").write_text(
            "approved: true\n  bad: indent: here\n", encoding="utf-8"
        )
        result = phase_gate(_p("02-Architecture/01-UX/01-tokens.md"), repo_root=tmp_path)
        assert result.decision == "deny"
        assert result.error_code == "phase_gate_violation"
        assert "corrupted" in (result.reason or "")


@pytest.mark.unit
class TestPhaseGateBypass:
    def test_bypass_allows_phase2_without_signoff(self, tmp_path) -> None:
        result = phase_gate(
            _p("02-Architecture/01-UX/01-tokens.md"),
            repo_root=tmp_path,
            bypass_phase_gate=True,
        )
        assert result.decision == "allow"

    def test_bypass_allows_phase3_without_signoff(self, tmp_path) -> None:
        result = phase_gate(
            _p("03-Implementation/01-API/server.py"),
            repo_root=tmp_path,
            bypass_phase_gate=True,
        )
        assert result.decision == "allow"
