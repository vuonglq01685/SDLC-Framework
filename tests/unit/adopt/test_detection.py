"""Unit tests for Pass 1 detection heuristics (Story 3.2, AC1-AC5, §2 TDD-first).

RED against the `return []` stub; GREEN once `detect_existing` is implemented.

Covers:
  * name-pattern scan: README / docs/**/*.md / .github/workflows/*.yml / pom.xml /
    Dockerfile / build files (AC1);
  * content heuristic: docs/*.md with C4/ADR headings -> kind=architecture (AC2);
  * classification into frozen taxonomy, confidence: int [0,100] -- NOT float (AC4);
  * suggested_target mapping per D1 decision table (AC4);
  * greenfield-disguised: empty tree -> detected: [] (AC5);
  * git_signal DI (D2) + legacy_code_globs exclusion (D4) + read-only smoke.

Test isolation: tmp_path, no live git -- git_signal injected as a fake map (D2 DI pattern).
`pytestmark = pytest.mark.unit` (rules/python/testing.md).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sdlc.adopt.passes.detection import detect_existing
from sdlc.contracts.adopt_report import ArtifactKind, DetectedArtifact

pytestmark = pytest.mark.unit


@pytest.fixture()
def repo_root(tmp_path: Path) -> Path:
    """A minimal empty repo root (no .claude/ state needed -- detection is read-only)."""
    return tmp_path


def _make_file(root: Path, rel: str, content: str = "") -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _paths(results: list[DetectedArtifact]) -> set[str]:
    return {r.path for r in results}


# ---------------------------------------------------------------------------
# AC1 -- name-pattern scan finds well-known artifacts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rel", "needle"),
    [
        ("README.md", "README.md"),
        (".github/workflows/ci.yml", "ci.yml"),
        (".github/workflows/deploy.yaml", "deploy.yaml"),
        ("pom.xml", "pom.xml"),
        ("Dockerfile", "Dockerfile"),
        ("pyproject.toml", "pyproject.toml"),
        ("package.json", "package.json"),
        ("go.mod", "go.mod"),
        ("build.gradle", "build.gradle"),
        ("docs/overview.md", "overview.md"),
    ],
)
def test_name_pattern_scan_finds_artifact(repo_root: Path, rel: str, needle: str) -> None:
    _make_file(repo_root, rel, "content")
    results = detect_existing(repo_root)
    assert any(needle in p for p in _paths(results)), f"{rel} not detected; got {_paths(results)}"


@pytest.mark.parametrize(
    ("skip_dir", "rel"),
    [
        (".claude", ".claude/docs/notes.md"),
        (".claude", ".claude/state/state.json"),
        (".git", ".git/config"),
        (".git", ".git/COMMIT_EDITMSG"),
    ],
)
def test_scan_skips_excluded_dirs(repo_root: Path, skip_dir: str, rel: str) -> None:
    _make_file(repo_root, rel, "x")
    results = detect_existing(repo_root)
    assert not any(skip_dir in p for p in _paths(results)), (
        f"{skip_dir}/ leaked into detected: {_paths(results)}"
    )


# ---------------------------------------------------------------------------
# AC2 -- content heuristics elevate kind + confidence
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rel", "content", "expected_kind", "min_conf"),
    [
        (
            "docs/design.md",
            "# Architecture\n\n## ADR-001: Use PostgreSQL\n\nDecision record.\n",
            "architecture",
            70,
        ),
        (
            "docs/arch.md",
            "# System Design\n\nC4 Context diagram.\n## Component diagram\n",
            "architecture",
            70,
        ),
        (
            "docs/requirements.md",
            "# Product Requirements Document\n\n## User Stories\n\nAs a user...\n",
            "prd",
            65,
        ),
        (
            "docs/ops.md",
            "# On-call Runbook\n\n## Incident Response\n\n## Escalation Procedures\n",
            "runbook",
            65,
        ),
        (
            "docs/research.md",
            "# Research Report\n\n## Findings\n\n## Analysis\n",
            "research",
            65,
        ),
    ],
)
def test_content_heuristic_classifies_doc(
    repo_root: Path, rel: str, content: str, expected_kind: ArtifactKind, min_conf: int
) -> None:
    _make_file(repo_root, rel, content)
    results = detect_existing(repo_root)
    matched = [r for r in results if r.kind == expected_kind]
    assert matched, f"No artifact classified as {expected_kind} for {rel}; got {results}"
    assert matched[0].confidence >= min_conf, (
        f"{expected_kind} confidence too low for {rel}: {matched[0].confidence}"
    )


# ---------------------------------------------------------------------------
# AC4 -- classification: valid DetectedArtifact + confidence is int (not float)
# ---------------------------------------------------------------------------


def test_all_results_are_valid_detected_artifact(repo_root: Path) -> None:
    _make_file(repo_root, "README.md", "# My Project")
    _make_file(repo_root, "pom.xml", "<project/>")
    _make_file(repo_root, "docs/arch.md", "# Architecture\n\nADR-001\n")
    results = detect_existing(repo_root)
    assert results, "No artifacts detected"
    assert all(isinstance(a, DetectedArtifact) for a in results)


def test_confidence_is_strict_int_in_range(repo_root: Path) -> None:
    """Binding correction: confidence must be int in [0,100], never a float like 0.92."""
    _make_file(repo_root, "README.md", "# My Project")
    _make_file(repo_root, "docs/arch.md", "# Architecture\n\nC4 diagram\n")
    _make_file(repo_root, "pom.xml", "<project/>")
    results = detect_existing(repo_root)
    assert results, "No artifacts detected"
    for a in results:
        assert type(a.confidence) is int, (
            f"confidence must be strict int, got {type(a.confidence).__name__} = {a.confidence!r}"
        )
        assert not isinstance(a.confidence, bool), "confidence must not be bool"
        assert 0 <= a.confidence <= 100, f"confidence out of [0,100]: {a.confidence}"


def test_all_kinds_are_valid_artifact_kind(repo_root: Path) -> None:
    for rel, content in [
        ("README.md", "# Proj"),
        (".github/workflows/ci.yml", "on: push"),
        ("pom.xml", "<project/>"),
        ("Dockerfile", "FROM python:3.12"),
        ("docs/arch.md", "# Architecture\n\nADR-001\n"),
        ("docs/prd.md", "# Product Requirements\n\nUser Story\n"),
    ]:
        _make_file(repo_root, rel, content)
    valid: set[ArtifactKind] = {
        "prd",
        "architecture",
        "research",
        "runbook",
        "ci-workflow",
        "build-file",
        "dockerfile",
        "readme",
        "unknown",
    }
    for a in detect_existing(repo_root):
        assert a.kind in valid, f"Invalid kind: {a.kind!r}"


# ---------------------------------------------------------------------------
# AC4 -- D1 suggested_target mapping table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rel", "content", "kind", "target"),
    [
        (
            "docs/PRD.md",
            "# Product Requirements Document\n\n## User Stories\n",
            "prd",
            "01-Requirement/01-PRODUCT.md",
        ),
        (
            "docs/arch.md",
            "# Architecture\n\nADR-001: decision\n",
            "architecture",
            "02-Architecture/02-System/ARCHITECTURE.md",
        ),
        (
            "docs/research.md",
            "# Research Report\n\n## Findings\n\n## Analysis\n",
            "research",
            "01-Requirement/02-Research/",
        ),
    ],
)
def test_mappable_kind_has_canonical_suggested_target(
    repo_root: Path, rel: str, content: str, kind: ArtifactKind, target: str
) -> None:
    _make_file(repo_root, rel, content)
    matched = [r for r in detect_existing(repo_root) if r.kind == kind]
    assert matched, f"No {kind} artifact detected for {rel}"
    assert matched[0].suggested_target == target, (
        f"{kind} suggested_target wrong: {matched[0].suggested_target!r}"
    )


def test_detect_only_kinds_have_empty_suggested_target(repo_root: Path) -> None:
    """runbook / ci-workflow / build-file / dockerfile / readme -> suggested_target == ''."""
    for rel, content in [
        ("README.md", "# My Project"),
        (".github/workflows/ci.yml", "on: push"),
        ("pom.xml", "<project/>"),
        ("Dockerfile", "FROM python:3.12"),
        ("docs/ops.md", "# On-call Runbook\n## Incident\n"),
    ]:
        _make_file(repo_root, rel, content)
    detect_only: set[ArtifactKind] = {
        "runbook",
        "ci-workflow",
        "build-file",
        "dockerfile",
        "readme",
    }
    for a in detect_existing(repo_root):
        if a.kind in detect_only:
            assert a.suggested_target == "", (
                f"kind={a.kind} should have empty suggested_target, got {a.suggested_target!r}"
            )


# ---------------------------------------------------------------------------
# AC5 -- greenfield-disguised: empty / source-only tree -> detected: []
# ---------------------------------------------------------------------------


def test_empty_repo_returns_empty_list(repo_root: Path) -> None:
    assert detect_existing(repo_root) == []


def test_source_only_repo_returns_empty_list(repo_root: Path) -> None:
    _make_file(repo_root, "src/app.py", "def main(): pass")
    _make_file(repo_root, "src/utils.py", "def helper(): ...")
    assert detect_existing(repo_root) == []


def test_dot_claude_only_returns_empty_list(repo_root: Path) -> None:
    _make_file(repo_root, ".claude/state/state.json", "{}")
    assert detect_existing(repo_root) == []


# ---------------------------------------------------------------------------
# D2 -- git_signal injection (recency boost)
# ---------------------------------------------------------------------------


def test_git_signal_boosts_recent_over_stale(repo_root: Path) -> None:
    _make_file(repo_root, "docs/arch.md", "# Architecture\n\nADR decision\n")
    recent = detect_existing(repo_root, git_signal={"docs/arch.md": 5})
    stale = detect_existing(repo_root, git_signal={"docs/arch.md": 200})
    recent_conf = next((r.confidence for r in recent if "arch.md" in r.path), None)
    stale_conf = next((r.confidence for r in stale if "arch.md" in r.path), None)
    assert recent_conf is not None and stale_conf is not None
    # Falsifiable: a `>=` here would still pass if the boost were removed (both collapse to the
    # base 85). Pin the exact +5 so a regressed/absent boost fails the test.
    assert recent_conf == stale_conf + 5, (
        f"recent={recent_conf} must equal stale={stale_conf} + 5 recency boost"
    )


def test_no_git_signal_degrades_gracefully(repo_root: Path) -> None:
    _make_file(repo_root, "README.md", "# My Project")
    results = detect_existing(repo_root)
    assert results and all(isinstance(r, DetectedArtifact) for r in results)


def test_empty_git_signal_degrades_gracefully(repo_root: Path) -> None:
    _make_file(repo_root, "pom.xml", "<project/>")
    assert detect_existing(repo_root, git_signal={})


# ---------------------------------------------------------------------------
# D4 -- legacy_code_globs exclusion
# ---------------------------------------------------------------------------


def test_legacy_code_glob_excludes_matching_paths(repo_root: Path) -> None:
    _make_file(repo_root, "src/legacy/README.md", "# Legacy Module")
    _make_file(repo_root, "README.md", "# Top-level README")
    excluded = detect_existing(repo_root, legacy_code_globs=("src/legacy/**",))
    excluded_paths = _paths(excluded)
    assert any("README.md" in p and "legacy" not in p for p in excluded_paths), (
        "Top-level README should not be excluded"
    )
    assert not any("legacy/README.md" in p for p in excluded_paths), (
        "src/legacy/README.md should be excluded by legacy_code_globs"
    )


def test_no_legacy_globs_same_as_empty_tuple(repo_root: Path) -> None:
    _make_file(repo_root, "pom.xml", "<project/>")
    a = detect_existing(repo_root)
    b = detect_existing(repo_root, legacy_code_globs=())
    assert sorted(_paths(a)) == sorted(_paths(b))


# ---------------------------------------------------------------------------
# Read-only smoke (lightweight local version of AC7)
# ---------------------------------------------------------------------------


def test_detection_writes_no_files(repo_root: Path) -> None:
    _make_file(repo_root, "README.md", "# My Project")
    _make_file(repo_root, "pom.xml", "<project/>")
    before = {str(p) for p in repo_root.rglob("*") if p.is_file()}
    detect_existing(repo_root)
    after = {str(p) for p in repo_root.rglob("*") if p.is_file()}
    new_outside_claude = {p for p in (after - before) if ".claude" not in p}
    assert not new_outside_claude, f"detect_existing created files: {new_outside_claude}"
