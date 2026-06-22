"""Unit tests for scripts/check_story_merged_before_done.py (Epic 3 retro A1).

RED phase per CONTRIBUTING §2 — tests describe the two rules this gate
enforces on every story newly flipped to ``done`` in sprint-status.yaml:

  R2 (merged-before-done): the story must have a per-story
     ``feat(<E.S>)``/``fix(<E.S>)`` commit reachable from HEAD — not left in
     the working tree, and not squashed under a coarse ``epic-*`` scope.

  R1 (tdd-ordering): a ``test(<E.S>)`` RED commit must precede the first
     GREEN commit in ``git log --reverse``. Waivable per-commit with a
     ``[tdd-along: <reason>]`` annotation for novel-substrate stories.

This gate codifies what the Epic 2B retro commissioned as action A2 but was
never built; its absence let Epic 3 ship 3.3/3.4 squashed (no per-story
test/feat) and 3.5 with no RED commit. GREEN lands in a follow-up commit.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest import mock

import pytest

import check_story_merged_before_done as gate

# ---------------------------------------------------------------------------
# is_story_key — only real stories are gated (not epics / retrospectives)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIsStoryKey:
    @pytest.mark.parametrize(
        "key",
        [
            "3-2-pass-1-detection-filesystem-scan-content-heuristics",
            "4-1-sdlc-auto-orchestrator-auto-loop",
            "4-10-auto-brainstorm-panel-dispatch-on-ambiguity",
            "2a-1-workflow-yaml-loader-schema-validation",
            "2b-11-author-support-specialists",
            "1-18-1-cli-trace-replay-logs-quality-hardening",
        ],
    )
    def test_real_story_keys_are_gated(self, key: str) -> None:
        assert gate.is_story_key(key) is True

    @pytest.mark.parametrize(
        "key",
        [
            "epic-3",
            "epic-3-retrospective",
            "epic-4",
            "epic-4-retrospective",
        ],
    )
    def test_epic_and_retro_keys_are_not_gated(self, key: str) -> None:
        assert gate.is_story_key(key) is False


# ---------------------------------------------------------------------------
# derive_scope_candidates — story key -> commit-scope token(s)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDeriveScopeCandidates:
    def test_simple_story(self) -> None:
        assert "3.2" in gate.derive_scope_candidates("3-2-pass-1-detection")

    def test_double_digit_story(self) -> None:
        assert "4.10" in gate.derive_scope_candidates("4-10-auto-brainstorm-panel")

    def test_lettered_epic(self) -> None:
        assert "2a.1" in gate.derive_scope_candidates("2a-1-workflow-yaml-loader")

    def test_sub_story_offers_both_spellings(self) -> None:
        cands = gate.derive_scope_candidates("1-18-1-cli-trace-replay-logs")
        assert "1.18" in cands
        assert "1.18.1" in cands

    def test_slug_number_is_not_mistaken_for_substory(self) -> None:
        # "3-2-pass-1-..." — the "1" after "pass" is slug text, not a sub-story.
        cands = gate.derive_scope_candidates("3-2-pass-1-detection")
        assert "3.2" in cands
        assert "3.2.pass" not in cands


# ---------------------------------------------------------------------------
# diff_newly_done — which stories flipped to done in this commit
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDiffNewlyDone:
    def test_status_flipped_to_done_is_detected(self) -> None:
        head = {"4-1-foo": "in-progress"}
        staged = {"4-1-foo": "done"}
        assert gate.diff_newly_done(head, staged) == ["4-1-foo"]

    def test_already_done_is_not_re_flagged(self) -> None:
        head = {"4-1-foo": "done"}
        staged = {"4-1-foo": "done"}
        assert gate.diff_newly_done(head, staged) == []

    def test_brand_new_done_story_absent_from_head(self) -> None:
        head: dict[str, str] = {}
        staged = {"4-1-foo": "done"}
        assert gate.diff_newly_done(head, staged) == ["4-1-foo"]

    def test_epic_and_retrospective_flips_are_ignored(self) -> None:
        head = {"epic-4": "in-progress", "epic-3-retrospective": "optional"}
        staged = {"epic-4": "done", "epic-3-retrospective": "done"}
        assert gate.diff_newly_done(head, staged) == []

    def test_non_done_transitions_ignored(self) -> None:
        head = {"4-2-bar": "backlog"}
        staged = {"4-2-bar": "in-progress"}
        assert gate.diff_newly_done(head, staged) == []


# ---------------------------------------------------------------------------
# classify_story — read a per-story verdict out of git-log subjects
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestClassifyStory:
    def test_clean_red_then_green(self) -> None:
        subjects = ["test(4.1): RED — auto-loop", "feat(4.1): GREEN — auto-loop"]
        v = gate.classify_story("4-1-x", ("4.1",), subjects)
        assert (v.has_red, v.has_green, v.red_before_green) == (True, True, True)

    def test_green_without_red_like_story_3_5(self) -> None:
        subjects = ["feat(4.1): adopt rollback"]
        v = gate.classify_story("4-1-x", ("4.1",), subjects)
        assert v.has_green is True
        assert v.has_red is False
        assert v.red_before_green is False

    def test_squashed_under_epic_scope_like_3_3_3_4(self) -> None:
        # Only a coarse epic-scope feat exists; no per-story 4.1 commit.
        subjects = ["feat(epic-4): Pass 2 + Pass 3 (Stories 4.1-4.2)"]
        v = gate.classify_story("4-1-x", ("4.1",), subjects)
        assert v.has_green is False
        assert v.has_red is False

    def test_red_after_green_is_not_ordered(self) -> None:
        subjects = ["feat(4.1): GREEN", "test(4.1): RED added late"]
        v = gate.classify_story("4-1-x", ("4.1",), subjects)
        assert v.has_red is True
        assert v.has_green is True
        assert v.red_before_green is False

    def test_scope_boundary_is_anchored(self) -> None:
        # feat(4.10) must NOT satisfy story 4.1.
        subjects = ["test(4.10): RED", "feat(4.10): GREEN"]
        v = gate.classify_story("4-1-x", ("4.1",), subjects)
        assert v.has_green is False


# ---------------------------------------------------------------------------
# validate — aggregate pass/fail with R1 opt-out
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidate:
    def test_clean_story_passes(self) -> None:
        subjects = ["test(4.1): RED", "feat(4.1): GREEN"]
        result = gate.validate(["4-1-x"], subjects, "docs(4.1): status review->done")
        assert result.ok is True

    def test_missing_red_blocks(self) -> None:
        subjects = ["feat(4.1): GREEN only"]
        result = gate.validate(["4-1-x"], subjects, "docs(4.1): status review->done")
        assert result.ok is False
        assert "4-1-x" in result.reason

    def test_missing_red_waived_by_tdd_along(self) -> None:
        subjects = ["feat(4.1): novel substrate, test-along"]
        msg = "docs(4.1): status review->done [tdd-along: test API designed in-story]"
        result = gate.validate(["4-1-x"], subjects, msg)
        assert result.ok is True

    def test_squash_blocks_even_with_tdd_along(self) -> None:
        # R2 (a per-story feat must exist) is never waivable.
        subjects = ["feat(epic-4): squashed 4.1+4.2"]
        msg = "docs: flip done [tdd-along: whatever]"
        result = gate.validate(["4-1-x"], subjects, msg)
        assert result.ok is False
        assert "4-1-x" in result.reason

    def test_one_bad_story_among_many_fails_the_batch(self) -> None:
        subjects = [
            "test(4.1): RED",
            "feat(4.1): GREEN",
            "feat(4.2): GREEN no red",
        ]
        result = gate.validate(["4-1-x", "4-2-y"], subjects, "docs: flip both done")
        assert result.ok is False
        assert "4-2-y" in result.reason
        assert "4-1-x" not in result.reason


# ---------------------------------------------------------------------------
# parse_development_status — pull the status map out of sprint-status.yaml
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestParseDevelopmentStatus:
    def test_parses_status_map(self) -> None:
        text = "schema_version: 1\ndevelopment_status:\n  4-1-foo: done\n  4-2-bar: in-progress\n"
        statuses = gate.parse_development_status(text)
        assert statuses["4-1-foo"] == "done"
        assert statuses["4-2-bar"] == "in-progress"

    def test_empty_text_yields_empty_map(self) -> None:
        assert gate.parse_development_status("") == {}


# ---------------------------------------------------------------------------
# main — CLI wiring + exit codes
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMain:
    def test_missing_argv_returns_2(self) -> None:
        assert gate.main([]) == 2

    def test_noop_when_sprint_status_not_staged(self, tmp_path: Path) -> None:
        msg = tmp_path / "COMMIT_EDITMSG"
        msg.write_text("feat(4.1): something unrelated", encoding="utf-8")
        with mock.patch.object(gate, "_staged_paths", return_value=["src/sdlc/x.py"]):
            assert gate.main([str(msg)]) == 0

    def test_clean_flip_passes(self, tmp_path: Path) -> None:
        msg = tmp_path / "COMMIT_EDITMSG"
        msg.write_text("docs(4.1): status review->done", encoding="utf-8")
        with (
            mock.patch.object(gate, "_staged_paths", return_value=[gate.SPRINT_STATUS_PATH]),
            mock.patch.object(
                gate, "_blob_at_head", return_value="development_status:\n  4-1-x: in-progress\n"
            ),
            mock.patch.object(
                gate, "_blob_at_index", return_value="development_status:\n  4-1-x: done\n"
            ),
            mock.patch.object(
                gate, "_git_log_subjects", return_value=["test(4.1): RED", "feat(4.1): GREEN"]
            ),
        ):
            assert gate.main([str(msg)]) == 0

    def test_violation_blocks_with_exit_1(self, tmp_path: Path) -> None:
        msg = tmp_path / "COMMIT_EDITMSG"
        msg.write_text("docs(4.1): status review->done", encoding="utf-8")
        with (
            mock.patch.object(gate, "_staged_paths", return_value=[gate.SPRINT_STATUS_PATH]),
            mock.patch.object(
                gate, "_blob_at_head", return_value="development_status:\n  4-1-x: in-progress\n"
            ),
            mock.patch.object(
                gate, "_blob_at_index", return_value="development_status:\n  4-1-x: done\n"
            ),
            mock.patch.object(gate, "_git_log_subjects", return_value=["feat(4.1): GREEN no red"]),
        ):
            assert gate.main([str(msg)]) == 1


# ---------------------------------------------------------------------------
# _run_git UTF-8 decode contract — Windows cp1252 false-pass guard (Epic 4 retro A2)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRunGitDecodesUtf8:
    """Regression for the Windows cp1252 false-pass (Epic 4 retro A2).

    ``subprocess.run(..., text=True)`` with no ``encoding=`` decodes git stdout
    using the locale default (cp1252 on Windows), which mojibakes the UTF-8
    em-dashes ubiquitous in this repo's commit subjects. The gate then reads
    garbled/empty subjects and false-passes (rc=0, validates nothing) —
    reproducing the exact Epic-3 "looks-green-but-didn't-run" failure on a new
    platform. The fix pins ``encoding="utf-8"`` on every git subprocess.
    """

    def test_run_git_pins_utf8_encoding(self) -> None:
        captured: dict[str, object] = {}

        def fake_run(cmd: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            captured.update(kwargs)
            return subprocess.CompletedProcess([], 0, stdout="", stderr="")

        with mock.patch.object(gate.subprocess, "run", side_effect=fake_run):
            gate._run_git(["log", "--reverse", "--pretty=%s"])

        assert captured.get("encoding") == "utf-8"

    def test_em_dash_subjects_round_trip(self) -> None:
        # Reproduce CPython text-mode decoding on any host: with encoding unset
        # the Windows default (cp1252) mojibakes the UTF-8 em-dash; utf-8 round-trips.
        raw = "feat(4.1): GREEN — auto-loop".encode()

        def fake_run(cmd: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            enc = kwargs.get("encoding") or "cp1252"
            return subprocess.CompletedProcess([], 0, stdout=raw.decode(str(enc)), stderr="")

        with mock.patch.object(gate.subprocess, "run", side_effect=fake_run):
            subjects = gate._git_log_subjects()

        assert subjects == ["feat(4.1): GREEN — auto-loop"]
