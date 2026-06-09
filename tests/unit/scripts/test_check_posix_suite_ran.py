"""Unit tests for scripts/check_posix_suite_ran.py (Epic 3 retro A2).

RED phase per CONTRIBUTING §2. This gate institutionalizes the defining Epic 3
lesson: the adopt suite is POSIX-only (ADR-034) and ``skip``s on win32, so a run
where *every* adopt test skipped is a false green, not a pass. On a POSIX CI
runner the suite MUST actually execute. Tests describe the JUnit-XML parsing and
the executed-floor decision; GREEN lands in a follow-up commit.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

import check_posix_suite_ran as gate

# A minimal pytest-style JUnit document: 3 testcases, 1 skipped.
_XML_RAN = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="3" skipped="1" failures="0" errors="0">
    <testcase classname="tests.unit.adopt.test_driver" name="test_a"/>
    <testcase classname="tests.unit.adopt.test_driver" name="test_b"/>
    <testcase classname="tests.unit.adopt.test_stamp" name="test_c">
      <skipped message="POSIX-only (ADR-034)" type="pytest.skip"/>
    </testcase>
  </testsuite>
</testsuites>
"""

# Every testcase skipped — the false-green shape the gate must catch.
_XML_ALL_SKIPPED = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="2" skipped="2" failures="0" errors="0">
    <testcase classname="tests.unit.adopt.test_driver" name="test_a">
      <skipped message="win32" type="pytest.skip"/>
    </testcase>
    <testcase classname="tests.unit.adopt.test_stamp" name="test_b">
      <skipped message="win32" type="pytest.skip"/>
    </testcase>
  </testsuite>
</testsuites>
"""

# No testcases at all — wrong path or a collection error masked the suite.
_XML_EMPTY = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="0"/></testsuites>
"""


# ---------------------------------------------------------------------------
# parse_junit — count collected vs skipped from JUnit XML
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestParseJunit:
    def test_counts_collected_and_skipped(self) -> None:
        outcome = gate.parse_junit(_XML_RAN)
        assert outcome.collected == 3
        assert outcome.skipped == 1
        assert outcome.executed == 2

    def test_all_skipped(self) -> None:
        outcome = gate.parse_junit(_XML_ALL_SKIPPED)
        assert outcome.collected == 2
        assert outcome.skipped == 2
        assert outcome.executed == 0

    def test_empty_suite(self) -> None:
        outcome = gate.parse_junit(_XML_EMPTY)
        assert outcome.collected == 0
        assert outcome.executed == 0

    def test_blank_text_is_zero(self) -> None:
        outcome = gate.parse_junit("")
        assert outcome.collected == 0


# ---------------------------------------------------------------------------
# evaluate — the executed-floor decision
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEvaluate:
    def test_suite_that_ran_passes(self) -> None:
        result = gate.evaluate(gate.SuiteOutcome(collected=3, skipped=1), min_executed=1)
        assert result.ok is True

    def test_all_skipped_is_false_green(self) -> None:
        result = gate.evaluate(gate.SuiteOutcome(collected=200, skipped=200), min_executed=1)
        assert result.ok is False
        assert "skipped" in result.reason.lower()

    def test_no_collection_blocks(self) -> None:
        result = gate.evaluate(gate.SuiteOutcome(collected=0, skipped=0), min_executed=1)
        assert result.ok is False
        assert "collect" in result.reason.lower()

    def test_under_floor_blocks(self) -> None:
        # 5 executed but the runner expects at least 50 — partial-skip regression.
        result = gate.evaluate(gate.SuiteOutcome(collected=205, skipped=200), min_executed=50)
        assert result.ok is False


# ---------------------------------------------------------------------------
# main — CLI wiring + exit codes
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMain:
    def test_reads_existing_junit_and_passes(self, tmp_path: Path) -> None:
        report = tmp_path / "adopt-junit.xml"
        report.write_text(_XML_RAN, encoding="utf-8")
        assert gate.main(["--junitxml", str(report)]) == 0

    def test_reads_existing_junit_and_blocks(self, tmp_path: Path) -> None:
        report = tmp_path / "adopt-junit.xml"
        report.write_text(_XML_ALL_SKIPPED, encoding="utf-8")
        assert gate.main(["--junitxml", str(report)]) == 1

    def test_runs_suite_when_no_report_given(self, tmp_path: Path) -> None:
        # When no --junitxml is supplied the gate runs the suite itself; mock
        # that out and assert it parses what the run produced.
        def _fake_run(paths: list[str], out_path: Path) -> int:
            out_path.write_text(_XML_RAN, encoding="utf-8")
            return 0

        with mock.patch.object(gate, "_run_pytest_to_junit", side_effect=_fake_run):
            assert gate.main([]) == 0
