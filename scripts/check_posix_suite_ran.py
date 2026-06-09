"""POSIX adopt-suite-actually-ran gate (Epic 3 retro action A2).

The adopt module is POSIX-only (ADR-034): every adopt/property test carries a
``pytest.skip`` on win32. The defining lesson of Epic 3 is that a run where the
whole adopt suite *skipped* is a false green, not a pass — the dev host was
Windows, the suite silently skipped, and the verification debt detonated in 3.7.

This gate makes that invariant explicit and permanent. On a POSIX CI runner the
adopt suite MUST actually execute: it reads a JUnit-XML report (pytest's built-in
``--junitxml``) and fails if zero tests were collected (wrong path / collection
error) or fewer than ``--min-executed`` tests actually ran (the rest skipped).
If a future CI matrix adds a win32 cell, or a skip marker broadens to skip on
POSIX too, an all-skipped run becomes a hard red here instead of a misleading
green.

Companion to the ``mutation-tests`` job (``scripts/run_adopt_mutation.py``,
>=95% kill). Both are the "POSIX pre-merge gate" the Epic 3 retro commissioned;
both must be marked as required status checks for ``main`` (see ADR-006).

Usage:
  python scripts/check_posix_suite_ran.py [--junitxml PATH] [--min-executed N]
                                          [--paths P ...]
Without ``--junitxml`` the gate runs the suite itself to a temp report.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]

# The POSIX-only suites this gate proves actually ran. The unit/adopt tree is
# the core (fast); property tests are slower but exercise the same invariant.
_DEFAULT_PATHS: Final[tuple[str, ...]] = ("tests/unit/adopt",)

# Minimum executed (non-skipped) tests required to treat the run as real. The
# default of 1 catches the catastrophic all-skipped false green; CI may raise it
# to a meaningful floor (the adopt suite runs in the hundreds on a POSIX host).
_DEFAULT_MIN_EXECUTED: Final[int] = 1

# ``_run_pytest_to_junit`` returns this when pytest itself failed to launch
# (distinct from ordinary test failures, which still produce a JUnit report).
_PYTEST_LAUNCH_ERROR: Final[int] = 2


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reason: str  # empty when ok


@dataclass(frozen=True)
class SuiteOutcome:
    collected: int
    skipped: int

    @property
    def executed(self) -> int:
        return self.collected - self.skipped


def parse_junit(xml_text: str) -> SuiteOutcome:
    """Count collected vs skipped testcases from a JUnit-XML report.

    Counts ``<testcase>`` elements directly (and ``<skipped>`` children) rather
    than trusting the ``tests``/``skipped`` summary attributes, which vary in
    presence across pytest versions.
    """
    if not xml_text.strip():
        return SuiteOutcome(collected=0, skipped=0)
    root = ET.fromstring(xml_text)
    testcases = list(root.iter("testcase"))
    skipped = sum(1 for case in testcases if case.find("skipped") is not None)
    return SuiteOutcome(collected=len(testcases), skipped=skipped)


def evaluate(outcome: SuiteOutcome, min_executed: int) -> ValidationResult:
    """Fail unless the POSIX suite actually ran a non-trivial number of tests."""
    if outcome.collected == 0:
        return ValidationResult(
            ok=False,
            reason=(
                "no adopt tests were collected — a wrong path or a collection error "
                "masked the suite. The POSIX adopt suite must run on this runner."
            ),
        )
    if outcome.executed < min_executed:
        return ValidationResult(
            ok=False,
            reason=(
                f"POSIX-only adopt suite did not run: {outcome.executed} executed of "
                f"{outcome.collected} collected ({outcome.skipped} skipped, "
                f"floor {min_executed}). On a POSIX host an all-/mostly-skipped adopt "
                "run is a FALSE GREEN (Epic 3 retro A2 / ADR-034). Verify the win32 "
                "skip markers are not firing on POSIX and the runner is Linux/macOS."
            ),
        )
    return ValidationResult(ok=True, reason="")


def _run_pytest_to_junit(paths: list[str], out_path: Path) -> int:
    """Run the given test paths producing a JUnit report at ``out_path``.

    Returns the pytest exit code (0 = all passed, 5 = no tests collected, etc.).
    Coverage is disabled — this gate cares only about executed-vs-skipped.
    """
    try:
        result = subprocess.run(
            [
                "uv",
                "run",
                "pytest",
                *paths,
                "--no-cov",
                "-p",
                "no:cacheprovider",
                f"--junitxml={out_path}",
                "-q",
            ],
            cwd=_REPO_ROOT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"ERROR: failed to run pytest: {exc}", file=sys.stderr)
        return 2
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    """CLI entry.

    Exit codes:
      0 — the POSIX adopt suite ran (>= min-executed tests executed)
      1 — false green: nothing collected, or too many tests skipped
      2 — IO/usage error (unreadable report, pytest failed to launch)
    """
    parser = argparse.ArgumentParser(description="POSIX adopt-suite-ran gate (Epic 3 retro A2).")
    parser.add_argument(
        "--junitxml",
        type=Path,
        default=None,
        help="Existing JUnit report to inspect. If omitted, the suite is run.",
    )
    parser.add_argument(
        "--min-executed",
        type=int,
        default=_DEFAULT_MIN_EXECUTED,
        help=f"Minimum executed (non-skipped) tests (default: {_DEFAULT_MIN_EXECUTED}).",
    )
    parser.add_argument(
        "--paths",
        nargs="+",
        default=list(_DEFAULT_PATHS),
        help=f"Test paths to run when --junitxml is omitted (default: {' '.join(_DEFAULT_PATHS)}).",
    )
    args = parser.parse_args(argv)

    report_path: Path | None = args.junitxml
    if report_path is None:
        tmp = Path(tempfile.mkdtemp(prefix="posix-suite-ran-")) / "junit.xml"
        rc = _run_pytest_to_junit(args.paths, tmp)
        if rc == _PYTEST_LAUNCH_ERROR:
            return 2
        report_path = tmp

    try:
        xml_text = report_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        print(f"ERROR: cannot read JUnit report {report_path}: {exc}", file=sys.stderr)
        return 2

    result = evaluate(parse_junit(xml_text), args.min_executed)
    if result.ok:
        return 0

    print(
        "BLOCKED by check_posix_suite_ran (Epic 3 retro action A2 / ADR-034)",
        file=sys.stderr,
    )
    print(f"  {result.reason}", file=sys.stderr)
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
