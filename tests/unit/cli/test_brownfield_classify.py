"""Unit tests for the deterministic brownfield TDD-strategy classifier (Story 3.8, AC1/D2(a)).

The classifier matches a task's ``touches`` paths against ``legacy_code_globs`` and stamps
``tdd_strategy``. Glob-matching is CLI-side (NOT the LLM) so the mock-vs-claude byte identity
holds (2B.3). Greenfield (empty globs) MUST always yield ``write-tests-first`` (regression guard).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Greenfield regression: empty legacy_code_globs → always write-tests-first.
# ---------------------------------------------------------------------------


def test_empty_globs_yields_write_tests_first_even_with_touches() -> None:
    from sdlc.cli._brownfield import classify_tdd_strategy

    assert (
        classify_tdd_strategy(("src/legacy/foo.py", "src/main/java/App.java"), ())
        == "write-tests-first"
    )


def test_empty_touches_yields_write_tests_first() -> None:
    from sdlc.cli._brownfield import classify_tdd_strategy

    assert classify_tdd_strategy((), ("src/legacy/**",)) == "write-tests-first"


def test_both_empty_yields_write_tests_first() -> None:
    from sdlc.cli._brownfield import classify_tdd_strategy

    assert classify_tdd_strategy((), ()) == "write-tests-first"


# ---------------------------------------------------------------------------
# Brownfield matches: any touched path under a legacy glob → characterization-test.
# ---------------------------------------------------------------------------


def test_single_glob_matches_direct_child() -> None:
    from sdlc.cli._brownfield import classify_tdd_strategy

    assert (
        classify_tdd_strategy(("src/legacy/foo.py",), ("src/legacy/**",)) == "characterization-test"
    )


def test_double_star_matches_deeply_nested_path() -> None:
    from sdlc.cli._brownfield import classify_tdd_strategy

    assert (
        classify_tdd_strategy(("src/legacy/sub/deep/bar.py",), ("src/legacy/**",))
        == "characterization-test"
    )


def test_double_star_matches_the_root_directory_itself() -> None:
    from sdlc.cli._brownfield import classify_tdd_strategy

    # ``src/legacy/**`` should also match the bare directory ``src/legacy``.
    assert classify_tdd_strategy(("src/legacy",), ("src/legacy/**",)) == "characterization-test"


def test_any_matching_touch_promotes_the_whole_task() -> None:
    from sdlc.cli._brownfield import classify_tdd_strategy

    # One non-legacy + one legacy path → characterization-test (any-match semantics).
    assert (
        classify_tdd_strategy(("src/app/new.py", "src/legacy/old.py"), ("src/legacy/**",))
        == "characterization-test"
    )


def test_multiple_globs_second_one_matches() -> None:
    from sdlc.cli._brownfield import classify_tdd_strategy

    assert (
        classify_tdd_strategy(("src/main/java/App.java",), ("src/legacy/**", "src/main/java/**"))
        == "characterization-test"
    )


def test_exact_path_glob_matches_itself() -> None:
    from sdlc.cli._brownfield import classify_tdd_strategy

    assert (
        classify_tdd_strategy(("src/main/java/App.java",), ("src/main/java/App.java",))
        == "characterization-test"
    )


# ---------------------------------------------------------------------------
# Non-matches: segment-aware semantics (``*`` does not cross ``/``).
# ---------------------------------------------------------------------------


def test_no_match_yields_write_tests_first() -> None:
    from sdlc.cli._brownfield import classify_tdd_strategy

    assert classify_tdd_strategy(("src/app/feature.py",), ("src/legacy/**",)) == "write-tests-first"


def test_single_star_does_not_cross_slash() -> None:
    from sdlc.cli._brownfield import classify_tdd_strategy

    # ``src/legacy/*.py`` matches a direct child but NOT a nested file.
    assert (
        classify_tdd_strategy(("src/legacy/foo.py",), ("src/legacy/*.py",))
        == "characterization-test"
    )
    assert (
        classify_tdd_strategy(("src/legacy/sub/foo.py",), ("src/legacy/*.py",))
        == "write-tests-first"
    )


def test_prefix_is_not_a_substring_match() -> None:
    from sdlc.cli._brownfield import classify_tdd_strategy

    # ``src/legacy`` must not match ``src/legacy_helpers/...`` (segment boundary).
    assert (
        classify_tdd_strategy(("src/legacy_helpers/foo.py",), ("src/legacy/**",))
        == "write-tests-first"
    )
