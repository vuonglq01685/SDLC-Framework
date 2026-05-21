"""Unit tests for scripts/check_fresh_context_review_tag.py (C7 / retro A2).

RED phase per CONTRIBUTING §2 — tests describe R1 (tag required when review
commit) and R2 (review commits must not touch src/), plus CLI wiring.
GREEN lands in a follow-up commit.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

import check_fresh_context_review_tag as gate

# ---------------------------------------------------------------------------
# detect_review_keywords — R1 trigger detection
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDetectReviewKeywords:
    @pytest.mark.parametrize(
        "message",
        [
            "chore(2A.18): code-review patches applied, status → done",
            "Apply review patches from Round-2",
            "review patches applied (P1-P6)",
            "Chunked review feedback applied",
            "BMAD-code-review output",
            "Run bmad-code-review on dispatcher module",
        ],
    )
    def test_review_phrases_detected(self, message: str) -> None:
        assert gate.detect_review_keywords(message) is True

    @pytest.mark.parametrize(
        "message",
        [
            "feat(2A.19): /sdlc-replan mark-stale + invalidate-downstream",
            "fix: rename variable in dispatcher",
            "docs: add ADR-028 stub",
            "test: red tests for engine helper",
            "chore: bump uv lock",
            # 'preview' contains 'review' as substring but should NOT trigger.
            "feat: add link-preview rendering",
        ],
    )
    def test_non_review_messages_not_detected(self, message: str) -> None:
        assert gate.detect_review_keywords(message) is False


# ---------------------------------------------------------------------------
# has_fresh_context_tag — literal tag detection
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHasFreshContextTag:
    def test_tag_present_in_subject(self) -> None:
        msg = "[fresh-context-review] chore(2A.18): apply review patches"
        assert gate.has_fresh_context_tag(msg) is True

    def test_tag_present_in_body(self) -> None:
        msg = "chore(2A.18): code-review patches applied\n\n[fresh-context-review]"
        assert gate.has_fresh_context_tag(msg) is True

    def test_tag_absent(self) -> None:
        msg = "chore(2A.18): code-review patches applied"
        assert gate.has_fresh_context_tag(msg) is False

    def test_tag_case_sensitive(self) -> None:
        # Tag is a fixed string and must be byte-exact — capitalisation drift
        # would weaken the audit signal.
        msg = "[Fresh-Context-Review] applied"
        assert gate.has_fresh_context_tag(msg) is False


# ---------------------------------------------------------------------------
# partition_staged — file-prefix split
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPartitionStaged:
    def test_all_tests_files_allowed(self) -> None:
        files = ["tests/unit/foo.py", "tests/integration/bar.py"]
        allowed, disallowed = gate.partition_staged(files)
        assert allowed == files
        assert disallowed == []

    def test_src_files_disallowed(self) -> None:
        files = ["src/sdlc/cli/foo.py", "src/sdlc/engine/bar.py"]
        allowed, disallowed = gate.partition_staged(files)
        assert allowed == []
        assert disallowed == files

    def test_mixed_partitioned(self) -> None:
        files = [
            "src/sdlc/cli/foo.py",
            "tests/unit/foo.py",
            "_bmad-output/sprint-status.yaml",
            "src/sdlc/engine/bar.py",
        ]
        allowed, disallowed = gate.partition_staged(files)
        assert allowed == ["tests/unit/foo.py", "_bmad-output/sprint-status.yaml"]
        assert disallowed == ["src/sdlc/cli/foo.py", "src/sdlc/engine/bar.py"]

    def test_docs_and_contributing_allowed(self) -> None:
        files = [
            "docs/decisions/ADR-029-foo.md",
            "CONTRIBUTING.md",
            "README.md",
            "scripts/check_foo.py",
        ]
        allowed, disallowed = gate.partition_staged(files)
        assert allowed == files
        assert disallowed == []

    def test_empty_files_list(self) -> None:
        allowed, disallowed = gate.partition_staged([])
        assert allowed == []
        assert disallowed == []


# ---------------------------------------------------------------------------
# validate — composed R1 + R2
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidate:
    def test_non_review_commit_passes_regardless_of_staged(self) -> None:
        # No review keywords → R1 doesn't trigger; tag absence is fine;
        # src/ modifications are fine because it's a real implementation commit.
        result = gate.validate(
            "feat(2A.19): /sdlc-replan mark-stale",
            staged_files=["src/sdlc/cli/replan_cmd.py", "tests/unit/cli/test_replan.py"],
        )
        assert result.ok is True

    def test_review_commit_missing_tag_fails_r1(self) -> None:
        result = gate.validate(
            "chore(2A.18): code-review patches applied",
            staged_files=["tests/unit/cli/test_next.py"],
        )
        assert result.ok is False
        assert "fresh-context-review" in result.reason.lower()

    def test_review_commit_with_tag_no_src_passes(self) -> None:
        result = gate.validate(
            "[fresh-context-review] chore(2A.18): code-review patches applied",
            staged_files=["tests/unit/cli/test_next.py", "_bmad-output/deferred-work.md"],
        )
        assert result.ok is True

    def test_tagged_commit_with_src_modification_fails_r2(self) -> None:
        result = gate.validate(
            "[fresh-context-review] chore(2A.18): apply review patches",
            staged_files=["src/sdlc/cli/next_.py"],
        )
        assert result.ok is False
        assert "src/" in result.reason

    def test_tagged_commit_with_mixed_staged_lists_offending_files(self) -> None:
        # If R2 fails, the reason must enumerate at least one offending file
        # so the operator can act without re-running git diff.
        result = gate.validate(
            "[fresh-context-review] chore(2A.18): apply review patches",
            staged_files=[
                "tests/unit/cli/test_next.py",
                "src/sdlc/cli/next_.py",
                "_bmad-output/deferred-work.md",
            ],
        )
        assert result.ok is False
        assert "src/sdlc/cli/next_.py" in result.reason


# ---------------------------------------------------------------------------
# main — CLI exit codes via commit-msg-file argument
# ---------------------------------------------------------------------------


def _write_msg(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "COMMIT_EDITMSG"
    path.write_text(body, encoding="utf-8")
    return path


@pytest.mark.unit
class TestMainCli:
    def test_passing_non_review_commit_exit_0(self, tmp_path: Path) -> None:
        msg_file = _write_msg(tmp_path, "feat(2A.19): /sdlc-replan mark-stale")
        with mock.patch.object(gate, "_read_staged_files", return_value=["src/sdlc/x.py"]):
            rc = gate.main([str(msg_file)])
        assert rc == 0

    def test_missing_tag_on_review_commit_exit_1(self, tmp_path: Path) -> None:
        msg_file = _write_msg(tmp_path, "chore(2A.18): code-review patches applied, status → done")
        with mock.patch.object(gate, "_read_staged_files", return_value=["tests/x.py"]):
            rc = gate.main([str(msg_file)])
        assert rc == 1

    def test_tagged_commit_clean_staged_exit_0(self, tmp_path: Path) -> None:
        msg_file = _write_msg(
            tmp_path,
            "[fresh-context-review] chore(2A.18): code-review patches applied",
        )
        with mock.patch.object(
            gate, "_read_staged_files", return_value=["tests/x.py", "CONTRIBUTING.md"]
        ):
            rc = gate.main([str(msg_file)])
        assert rc == 0

    def test_tagged_commit_with_src_exit_1(self, tmp_path: Path) -> None:
        msg_file = _write_msg(
            tmp_path,
            "[fresh-context-review] chore(2A.18): code-review patches applied",
        )
        with mock.patch.object(gate, "_read_staged_files", return_value=["src/sdlc/cli/next_.py"]):
            rc = gate.main([str(msg_file)])
        assert rc == 1

    def test_missing_commit_msg_file_exit_2(self, tmp_path: Path) -> None:
        rc = gate.main([str(tmp_path / "nope")])
        assert rc == 2


# ---------------------------------------------------------------------------
# Anti-tautology receipt (per ADR-026 §1)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAntiTautologyReceipt:
    def test_validate_is_load_bearing_in_main(self, tmp_path: Path) -> None:
        """Neutralise ``validate`` to a forced-pass; the otherwise-failing
        review-without-tag commit would still pass the CLI gate. If main
        returned 0 here, the wire from ``main`` to ``validate`` is broken
        and R1 enforcement is a tautology.
        """
        msg_file = _write_msg(tmp_path, "chore(2A.18): code-review patches applied")
        forced_pass = gate.ValidationResult(ok=True, reason="")
        with (
            mock.patch.object(gate, "validate", return_value=forced_pass),
            mock.patch.object(gate, "_read_staged_files", return_value=["tests/x.py"]),
        ):
            rc = gate.main([str(msg_file)])
        # Inverted assertion: with validate forced to pass, rc MUST be 0.
        # The genuine TestMainCli.test_missing_tag_on_review_commit_exit_1
        # is therefore confirmed to be exercising validate, not bypassed.
        assert rc == 0
