"""Tests for hooks/builtin/phase_gate.py (AC5, AC7, Story 2A.4 Task 4 + Story 2A.7 Task 6).

D2 decision (AC11): signoff_reader is injected by the dispatcher. Unit tests mock
the reader directly — no filesystem signoff state required. The reader contract is:
  Callable[[int, Path], str] → one of the SignoffState value strings.

Integration tests (test_phase_gate_signoff_read.py) verify the real compute_state wiring.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.contracts.hook_payload import HookPayload
from sdlc.hooks.builtin.phase_gate import phase_gate

# ---------------------------------------------------------------------------
# Reader fixtures — pure callables, no I/O
# ---------------------------------------------------------------------------


def _approved_reader(ph: int, rr: Path) -> str:
    return "approved"


def _awaiting_reader(ph: int, rr: Path) -> str:
    return "awaiting-signoff"


def _drafted_reader(ph: int, rr: Path) -> str:
    return "drafted-not-approved"


def _invalidated_reader(ph: int, rr: Path) -> str:
    return "invalidated-by-replan"


def _raising_reader(ph: int, rr: Path) -> str:
    raise RuntimeError("simulated reader error")


def _never_called(ph: int, rr: Path) -> str:
    raise AssertionError("signoff_reader must not be called for this path")


def _p(path: str) -> HookPayload:
    return HookPayload(
        hook_name="phase_gate",
        target_path=path,
        target_kind="write_intent",
        content_hash_before=None,
        write_intent="test write",
    )


# ---------------------------------------------------------------------------
# Phase 1 paths — always allow; reader is never consulted
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPhaseGatePhase1:
    def test_phase1_path_always_allows(self, tmp_path) -> None:
        result = phase_gate(
            _p("01-Requirement/04-Epics/EPIC-foo.json"),
            repo_root=tmp_path,
            signoff_reader=_never_called,
        )
        assert result.decision == "allow"

    def test_phase1_path_no_signoff_file_allows(self, tmp_path) -> None:
        result = phase_gate(
            _p("01-Requirement/01-PRODUCT.md"),
            repo_root=tmp_path,
            signoff_reader=_never_called,
        )
        assert result.decision == "allow"


# ---------------------------------------------------------------------------
# Phase 2 paths — gated on phase-1 signoff
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPhaseGatePhase2:
    def test_phase2_no_signoff_denies(self, tmp_path) -> None:
        result = phase_gate(
            _p("02-Architecture/01-UX/01-tokens.md"),
            repo_root=tmp_path,
            signoff_reader=_awaiting_reader,
        )
        assert result.decision == "deny"
        assert result.error_code == "phase_gate_violation"
        assert "not found" in (result.reason or "")

    def test_phase2_approved_false_denies(self, tmp_path) -> None:
        """Task 4.4 anti-tautology: drafted-not-approved must deny."""
        result = phase_gate(
            _p("02-Architecture/01-UX/01-tokens.md"),
            repo_root=tmp_path,
            signoff_reader=_drafted_reader,
        )
        assert result.decision == "deny"
        assert result.error_code == "phase_gate_violation"
        assert "drafted but not yet approved" in (result.reason or "")

    def test_phase2_approved_true_allows(self, tmp_path) -> None:
        result = phase_gate(
            _p("02-Architecture/01-UX/01-tokens.md"),
            repo_root=tmp_path,
            signoff_reader=_approved_reader,
        )
        assert result.decision == "allow"


# ---------------------------------------------------------------------------
# Phase 3 paths — gated on phase-2 signoff
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPhaseGatePhase3:
    def test_phase3_no_signoff_denies(self, tmp_path) -> None:
        result = phase_gate(
            _p("03-Implementation/01-API/server.py"),
            repo_root=tmp_path,
            signoff_reader=_awaiting_reader,
        )
        assert result.decision == "deny"
        assert result.error_code == "phase_gate_violation"
        assert "not found" in (result.reason or "")

    def test_phase3_approved_false_denies(self, tmp_path) -> None:
        result = phase_gate(
            _p("03-Implementation/01-API/server.py"),
            repo_root=tmp_path,
            signoff_reader=_drafted_reader,
        )
        assert result.decision == "deny"

    def test_phase3_approved_true_allows(self, tmp_path) -> None:
        result = phase_gate(
            _p("03-Implementation/01-API/server.py"),
            repo_root=tmp_path,
            signoff_reader=_approved_reader,
        )
        assert result.decision == "allow"


# ---------------------------------------------------------------------------
# Non-phase paths — always allow; reader is never consulted
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPhaseGateNonPhasePaths:
    def test_claude_state_path_allows(self, tmp_path) -> None:
        result = phase_gate(
            _p(".claude/state/signoffs/phase-1.yaml"),
            repo_root=tmp_path,
            signoff_reader=_never_called,
        )
        assert result.decision == "allow"

    def test_bmad_output_path_allows(self, tmp_path) -> None:
        result = phase_gate(
            _p("_bmad-output/planning-artifacts/prd.md"),
            repo_root=tmp_path,
            signoff_reader=_never_called,
        )
        assert result.decision == "allow"

    def test_tests_path_allows(self, tmp_path) -> None:
        result = phase_gate(
            _p("tests/unit/test_foo.py"),
            repo_root=tmp_path,
            signoff_reader=_never_called,
        )
        assert result.decision == "allow"

    def test_pyproject_toml_allows(self, tmp_path) -> None:
        result = phase_gate(
            _p("pyproject.toml"),
            repo_root=tmp_path,
            signoff_reader=_never_called,
        )
        assert result.decision == "allow"

    def test_signoff_record_write_allows(self, tmp_path) -> None:
        """Writing the signoff record itself (under .claude/) MUST be allowed (AC5 explicit)."""
        result = phase_gate(
            _p(".claude/state/signoffs/phase-2.yaml"),
            repo_root=tmp_path,
            signoff_reader=_never_called,
        )
        assert result.decision == "allow"


# ---------------------------------------------------------------------------
# Windows-style path handling
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPhaseGateWindowsPath:
    def test_windows_separator_still_gated(self, tmp_path) -> None:
        """PurePosixPath on Windows backslash paths: leading component still starts with '02-'."""
        result = phase_gate(
            _p("02-Architecture\\01-UX\\01-tokens.md"),
            repo_root=tmp_path,
            signoff_reader=_awaiting_reader,
        )
        # PurePosixPath treats backslash as a literal character, so
        # parts[0] == "02-Architecture\\01-UX\\01-tokens.md" — which still starts
        # with "02-". The gate therefore fires (conservatively correct: deny).
        assert result.decision == "deny"

    def test_posix_path_properly_gated(self, tmp_path) -> None:
        """Standard POSIX path is correctly gated."""
        result = phase_gate(
            _p("02-Architecture/01-UX/01-tokens.md"),
            repo_root=tmp_path,
            signoff_reader=_awaiting_reader,
        )
        assert result.decision == "deny"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPhaseGateEdgeCases:
    def test_empty_target_path_allows(self, tmp_path) -> None:
        """Empty string path → _get_leading_dir returns None → allow."""
        result = phase_gate(
            _p(""),
            repo_root=tmp_path,
            signoff_reader=_never_called,
        )
        assert result.decision == "allow"

    def test_non_dict_yaml_in_signoff_denies(self, tmp_path) -> None:
        """Reader that returns unexpected (non-approved) value → deny."""
        result = phase_gate(
            _p("02-Architecture/01-UX/01-tokens.md"),
            repo_root=tmp_path,
            signoff_reader=_awaiting_reader,
        )
        assert result.decision == "deny"
        assert result.error_code == "phase_gate_violation"

    def test_corrupted_yaml_signoff_denies(self, tmp_path) -> None:
        """Reader that raises (e.g. on malformed YAML) → fail-safe deny."""
        result = phase_gate(
            _p("02-Architecture/01-UX/01-tokens.md"),
            repo_root=tmp_path,
            signoff_reader=_raising_reader,
        )
        assert result.decision == "deny"
        assert result.error_code == "phase_gate_violation"
        assert "reader raised" in (result.reason or "")


# ---------------------------------------------------------------------------
# Bypass flag
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPhaseGateBypass:
    def test_bypass_allows_phase2_without_signoff(self, tmp_path) -> None:
        result = phase_gate(
            _p("02-Architecture/01-UX/01-tokens.md"),
            repo_root=tmp_path,
            bypass_phase_gate=True,
            signoff_reader=_never_called,
        )
        assert result.decision == "allow"

    def test_bypass_allows_phase3_without_signoff(self, tmp_path) -> None:
        result = phase_gate(
            _p("03-Implementation/01-API/server.py"),
            repo_root=tmp_path,
            bypass_phase_gate=True,
            signoff_reader=_never_called,
        )
        assert result.decision == "allow"
