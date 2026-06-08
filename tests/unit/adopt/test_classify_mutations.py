"""Mutation-kill tests for passes/_classify.py (Story 3.7 AC2, Tier-1).

Targets the 31 surviving mutants in _classify.py by exercising:
- Confidence constant exact values (_CONF_README=90, _CONF_CI=95, etc.)
- _RECENCY_BOOST=5 exact addition
- _RECENCY_DAYS=90 boundary (exactly 90 → boost, 91 → no boost)
- _MAX_CONF=100 cap (boost must not exceed 100)
- is_doc_markdown: 'docs' must be in parents (not in filename), suffix check
- _is_ci_workflow: contiguous '.github' + 'workflows' segments required
- _is_dockerfile: exact name patterns
- classify_markdown: priority order (arch > prd > runbook > research > unknown)
- suggested_target_for: exact target strings for prd/architecture/research
- matches_legacy_glob: segment-aware ** matching
"""

from __future__ import annotations

import pytest

from sdlc.adopt.passes._classify import (
    apply_recency_boost,
    classify_by_name,
    classify_markdown,
    is_doc_markdown,
    matches_legacy_glob,
    suggested_target_for,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Confidence constant exact values
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,expected_conf", [
    ("readme.md", 90),
    ("README.md", 90),
    ("README.rst", 90),
    ("Dockerfile", 95),
    ("dockerfile", 95),
    ("Dockerfile.prod", 95),
    ("service.dockerfile", 95),
    ("pom.xml", 95),
    ("pyproject.toml", 95),
    ("package.json", 95),
    ("go.mod", 95),
    ("build.gradle", 95),
    ("build.gradle.kts", 95),
])
def test_classify_by_name_returns_exact_confidence(name: str, expected_conf: int) -> None:
    """Each well-known filename maps to an exact confidence value (not +1 or -1)."""
    result = classify_by_name(name)
    assert result is not None
    _, conf = result
    assert conf == expected_conf, f"Expected confidence {expected_conf} for {name}, got {conf}"


@pytest.mark.parametrize("path,expected_kind,expected_conf", [
    (".github/workflows/ci.yml", "ci-workflow", 95),
    (".github/workflows/release.yaml", "ci-workflow", 95),
])
def test_ci_workflow_confidence_is_95(path: str, expected_kind: str, expected_conf: int) -> None:
    """CI workflow files get confidence 95 exactly."""
    result = classify_by_name(path)
    assert result is not None
    kind, conf = result
    assert kind == expected_kind
    assert conf == expected_conf


# ---------------------------------------------------------------------------
# apply_recency_boost exact values
# ---------------------------------------------------------------------------


def test_recency_boost_adds_exactly_5(  ) -> None:
    """apply_recency_boost adds exactly 5 when within recency window."""
    base_conf = 80
    signal = {"docs/arch.md": 30}  # 30 days ≤ 90 → boost
    result = apply_recency_boost(base_conf, "docs/arch.md", signal)
    assert result == 85  # 80 + 5


def test_recency_boost_not_applied_at_91_days(  ) -> None:
    """apply_recency_boost adds no boost when last-touched > 90 days."""
    signal = {"docs/arch.md": 91}
    result = apply_recency_boost(80, "docs/arch.md", signal)
    assert result == 80  # no boost


def test_recency_boost_applied_at_exactly_90_days(  ) -> None:
    """apply_recency_boost applies boost when days == 90 (boundary inclusive)."""
    signal = {"docs/arch.md": 90}
    result = apply_recency_boost(80, "docs/arch.md", signal)
    assert result == 85  # 80 + 5


def test_recency_boost_not_applied_at_zero_signal(  ) -> None:
    """apply_recency_boost returns unchanged confidence when path not in signal."""
    signal = {"other/file.md": 30}
    result = apply_recency_boost(80, "docs/arch.md", signal)
    assert result == 80


def test_recency_boost_caps_at_100(  ) -> None:
    """apply_recency_boost never returns > 100 (capped at _MAX_CONF)."""
    signal = {"docs/arch.md": 1}
    result = apply_recency_boost(97, "docs/arch.md", signal)
    assert result == 100  # 97 + 5 = 102 → capped to 100


def test_recency_boost_at_96_caps_to_100(  ) -> None:
    """apply_recency_boost(96, ...) → 100, not 101."""
    signal = {"docs/arch.md": 1}
    result = apply_recency_boost(96, "docs/arch.md", signal)
    assert result == 100


def test_recency_boost_at_95_returns_100(  ) -> None:
    """apply_recency_boost(95, ...) → 100, verifying cap is exactly 100."""
    signal = {"docs/arch.md": 1}
    result = apply_recency_boost(95, "docs/arch.md", signal)
    assert result == 100


def test_recency_boost_no_signal_no_boost(  ) -> None:
    """apply_recency_boost returns unchanged confidence when git_signal is None."""
    result = apply_recency_boost(85, "docs/arch.md", None)
    assert result == 85


# ---------------------------------------------------------------------------
# is_doc_markdown
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rel, expected", [
    ("docs/arch.md", True),
    ("docs/sub/research.md", True),
    ("docs/readme.rst", True),
    ("docs/file.markdown", True),
    ("docs/not-md.txt", False),         # wrong suffix
    ("src/docs/arch.md", True),          # docs can be nested
    ("README.md", False),               # no docs/ parent
    ("nodocs/arch.md", False),          # 'nodocs' is not 'docs'
])
def test_is_doc_markdown(rel: str, expected: bool) -> None:
    assert is_doc_markdown(rel) is expected


def test_is_doc_markdown_docs_in_filename_is_not_parent(  ) -> None:
    """A file named 'docs-arch.md' (without a docs/ directory) is NOT a doc markdown."""
    assert is_doc_markdown("project/docs-arch.md") is False


# ---------------------------------------------------------------------------
# CI workflow path detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path, should_match", [
    (".github/workflows/ci.yml", True),
    (".github/workflows/release.yaml", True),
    ("src/.github/workflows/ci.yml", True),   # nested repo
    (".github/ci.yml", False),                 # not under workflows/
    ("workflows/ci.yml", False),               # not under .github/
    (".github/workflows/readme.md", False),    # wrong suffix
    (".github/workflows/ci.json", False),      # json not yaml
])
def test_ci_workflow_detection(path: str, should_match: bool) -> None:
    result = classify_by_name(path)
    if should_match:
        assert result is not None
        assert result[0] == "ci-workflow"
    elif result is not None:
        assert result[0] != "ci-workflow"


# ---------------------------------------------------------------------------
# Dockerfile detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name, expected", [
    ("Dockerfile", True),
    ("dockerfile", True),
    ("DOCKERFILE", True),
    ("Dockerfile.dev", True),
    ("Dockerfile.prod", True),
    ("service.dockerfile", True),
    ("docker-compose.yml", False),
    ("Dockerfileignore", False),    # not a Dockerfile variant
])
def test_is_dockerfile_patterns(name: str, expected: bool) -> None:
    result = classify_by_name(name)
    if expected:
        assert result is not None
        assert result[0] == "dockerfile"
    elif result is not None:
        assert result[0] != "dockerfile"


# ---------------------------------------------------------------------------
# classify_markdown priority order
# ---------------------------------------------------------------------------


def test_classify_markdown_architecture_has_priority_over_prd(  ) -> None:
    """Content with both arch and PRD signatures → architecture wins (higher priority)."""
    content = "# ADR-001 product requirements user stories"
    kind, _ = classify_markdown(content)
    assert kind == "architecture"


def test_classify_markdown_prd_priority_over_runbook(  ) -> None:
    """Content with both PRD and runbook signatures → prd wins."""
    content = "user stories runbook incident"
    kind, _ = classify_markdown(content)
    assert kind == "prd"


def test_classify_markdown_runbook_priority_over_research(  ) -> None:
    """Content with both runbook and research signatures → runbook wins."""
    content = "runbook findings analysis"
    kind, _ = classify_markdown(content)
    assert kind == "runbook"


@pytest.mark.parametrize("content, expected_kind, expected_conf", [
    ("# ADR-001 Architecture Decision Record", "architecture", 85),
    ("c4 context diagram of the system", "architecture", 85),
    ("product requirements for the MVP", "prd", 80),
    ("user stories for sprint", "prd", 80),
    ("runbook for on-call procedures", "runbook", 75),
    ("research findings from the investigation", "research", 75),
    ("just some random document content", "unknown", 40),
])
def test_classify_markdown_kind_and_confidence(
    content: str, expected_kind: str, expected_conf: int
) -> None:
    """classify_markdown returns exact (kind, confidence) for each signature match."""
    kind, conf = classify_markdown(content)
    assert kind == expected_kind
    assert conf == expected_conf


# ---------------------------------------------------------------------------
# suggested_target_for
# ---------------------------------------------------------------------------


def test_suggested_target_prd(  ) -> None:
    assert suggested_target_for("prd") == "01-Requirement/01-PRODUCT.md"


def test_suggested_target_architecture(  ) -> None:
    assert suggested_target_for("architecture") == "02-Architecture/02-System/ARCHITECTURE.md"


def test_suggested_target_research(  ) -> None:
    assert suggested_target_for("research") == "01-Requirement/02-Research/"


def test_suggested_target_detect_only_returns_empty(  ) -> None:
    """Detect-only kinds (readme, ci-workflow, dockerfile, build-file, unknown) return ''."""
    for kind in ("readme", "ci-workflow", "dockerfile", "build-file", "unknown", "runbook"):
        assert suggested_target_for(kind) == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# matches_legacy_glob
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rel, patterns, expected", [
    ("src/legacy/old.py", ("src/legacy/**",), True),
    ("src/legacy/deep/nested.py", ("src/legacy/**",), True),
    ("src/main.py", ("src/legacy/**",), False),
    ("legacy/old.py", ("legacy/**",), True),
    ("src/old.py", ("src/*.py",), True),
    ("src/sub/old.py", ("src/*.py",), False),       # * doesn't cross dirs
    ("README.md", ("*.md",), True),
    ("docs/readme.md", ("*.md",), False),           # * doesn't cross
    ("docs/readme.md", ("**/*.md",), True),         # ** crosses dirs
    ("src/file.py", (), False),                     # empty globs → never matches
])
def test_matches_legacy_glob(rel: str, patterns: tuple[str, ...], expected: bool) -> None:
    assert matches_legacy_glob(rel, patterns) is expected


def test_matches_legacy_glob_empty_globs_always_false(  ) -> None:
    """matches_legacy_glob with empty tuple always returns False."""
    assert matches_legacy_glob("any/path/file.py", ()) is False


def test_matches_legacy_glob_double_star_any_depth(  ) -> None:
    """** glob matches arbitrarily deep paths."""
    assert matches_legacy_glob("a/b/c/d/e/f.py", ("a/**",)) is True
    assert matches_legacy_glob("a/b/c/d/e/f.py", ("**/f.py",)) is True


def test_matches_legacy_glob_slash_normalisation(  ) -> None:
    """Backslash patterns are normalised to forward slashes."""
    assert matches_legacy_glob("src/legacy/old.py", ("src\\legacy\\**",)) is True
