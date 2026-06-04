"""Integration test: `sdlc init --adopt` never modifies the source tree (Story 3.1/3.2/3.3).

After a full `sdlc init --adopt` on a minimal brownfield repo, `git status --porcelain`
reports no modification/deletion of any pre-existing tracked file. Story 3.1 (skeleton, no
detected artifacts) writes only under `.claude/`; Story 3.3 (Pass 2) additionally creates
canonical symlinks at SDLC slots — the one sanctioned write OUTSIDE `.claude/` (AC6) — so the
binding invariant is byte-identity of source files, not "nothing outside .claude/ changes". The
exhaustive multi-fixture porcelain + tree-hash property + mutation gate is Story 3.7; this is
the single-fixture smoke proof for the orchestrator + Pass 2.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

if sys.platform == "win32":  # pragma: no cover - adopt journals via POSIX-only writer
    pytest.skip("adopt mode is POSIX-only in v1 (ADR-034)", allow_module_level=True)

pytestmark = pytest.mark.integration

_runner = CliRunner()


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


@pytest.fixture
def brownfield_repo(tmp_path: Path) -> Path:
    """A committed git repo with a minimal pre-existing source tree."""
    if shutil.which("git") is None:  # pragma: no cover - git always present in CI
        pytest.skip("git not on PATH")
    root = tmp_path / "proj"
    root.mkdir()
    _git(["init"], root)
    _git(["config", "user.email", "test@example.com"], root)
    _git(["config", "user.name", "Test"], root)
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")
    (root / "README.md").write_text("# Existing project\n", encoding="utf-8")
    _git(["add", "-A"], root)
    _git(["commit", "-m", "initial"], root)
    return root


def test_adopt_does_not_touch_source_tree(
    brownfield_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdlc.cli.main import app

    monkeypatch.chdir(brownfield_repo)
    result = _runner.invoke(app, ["init", "--adopt"])
    assert result.exit_code == 0, result.output

    porcelain = _git(["status", "--porcelain"], brownfield_repo).stdout
    changed_paths = [line[3:] for line in porcelain.splitlines() if line.strip()]
    assert changed_paths, "expected adopt to create .claude/ artifacts"
    offenders = [p for p in changed_paths if not p.startswith(".claude/")]
    assert offenders == [], f"adopt modified paths outside .claude/: {offenders}"


def test_adopt_writes_adopt_report(brownfield_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from sdlc.cli.main import app

    monkeypatch.chdir(brownfield_repo)
    result = _runner.invoke(app, ["init", "--adopt"])
    assert result.exit_code == 0, result.output
    report_path = brownfield_repo / ".claude" / "state" / "adopt-report.json"
    assert report_path.exists()


def test_adopt_no_longer_reports_unimplemented(
    brownfield_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sdlc.cli.main import app

    monkeypatch.chdir(brownfield_repo)
    result = _runner.invoke(app, ["init", "--adopt"])
    assert "not implemented" not in result.output.lower()


# --- Story 3.2 AC7: Pass 1 detection is read-only over a real git brownfield repo ----------


@pytest.fixture
def brownfield_repo_with_artifacts(tmp_path: Path) -> Path:
    """A committed git repo with SDLC-shaped artifacts (README + arch doc + pom.xml)."""
    if shutil.which("git") is None:  # pragma: no cover - git always present in CI
        pytest.skip("git not on PATH")
    root = tmp_path / "proj"
    root.mkdir()
    _git(["init"], root)
    _git(["config", "user.email", "test@example.com"], root)
    _git(["config", "user.name", "Test"], root)
    # Hermetic: ignore any developer global gitignore (e.g. a `*.md` rule) so the README/arch
    # docs are actually tracked — otherwise git-recency has no entry for them and the AC3 boost
    # assertion below would silently depend on the host's global excludes.
    _git(["config", "core.excludesFile", "/dev/null"], root)
    (root / "src").mkdir()
    (root / "src" / "App.java").write_text("class App {}\n", encoding="utf-8")
    (root / "README.md").write_text("# Existing project\n", encoding="utf-8")
    (root / "pom.xml").write_text("<project/>\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "architecture.md").write_text(
        "# Architecture\n\n## ADR-001: PostgreSQL\n\nC4 Context diagram.\n", encoding="utf-8"
    )
    _git(["add", "-A"], root)
    _git(["commit", "-m", "initial"], root)
    return root


def test_adopt_detects_artifacts_without_touching_source(
    brownfield_repo_with_artifacts: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Full `sdlc init --adopt` detects + symlinks WITHOUT mutating any source (AC1/AC3/AC6).

    Runs end-to-end on a REAL git repo, so the live git-recency signal (D2, Story 3.2) and Pass 2
    (Story 3.3) are both exercised. Because the CliRunner stdin is not a TTY, Pass 2 runs
    non-interactively and auto-accepts the architecture doc (confidence 85 + 5 recency = 90 ≥ the
    default threshold 80), creating the canonical symlink at `02-Architecture/02-System/` — the ONE
    sanctioned write outside `.claude/` (AC6). The binding invariant is that every
    pre-existing SOURCE file stays byte-identical and is never replaced by a copy/symlink.
    """
    from sdlc.cli.main import app
    from sdlc.contracts.adopt_report import AdoptReport

    root = brownfield_repo_with_artifacts
    monkeypatch.chdir(root)
    # Snapshot every committed source file BEFORE adopt (NFR-REL-6 byte-identity check).
    source_rels = ("README.md", "pom.xml", "docs/architecture.md", "src/App.java")
    before = {rel: (root / rel).read_bytes() for rel in source_rels}

    result = _runner.invoke(app, ["init", "--adopt"])
    assert result.exit_code == 0, result.output

    # Detection ran and populated the report.
    report_path = root / ".claude" / "state" / "adopt-report.json"
    report = AdoptReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    kinds = {a.kind for a in report.detected}
    assert {"readme", "architecture", "build-file"} <= kinds, f"missing kinds; got {kinds}"

    # AC3 end-to-end: every artifact was just committed (days_since == 0 ≤ 90), so the live
    # git-recency signal must apply the +5 boost. README detected at the base 90 (not 95) would
    # mean the signal silently failed to thread through (e.g. path-key mismatch) — the kind set
    # above cannot catch that. This is the only test that exercises the real `git log` path.
    by_kind = {a.kind: a.confidence for a in report.detected}
    assert by_kind["readme"] == 95, (
        f"expected readme 90 base + 5 recency boost = 95, got {by_kind['readme']} "
        "(recency signal did not apply end-to-end)"
    )

    # AC6: every pre-existing source file is byte-identical and still a real file (not replaced).
    for rel, original in before.items():
        assert (root / rel).read_bytes() == original, f"source {rel} mutated"
        assert not (root / rel).is_symlink(), f"source {rel} was replaced by a symlink"

    # Pass 2 created the sanctioned arch symlink outside `.claude/` (the one allowed write).
    arch_link = root / "02-Architecture" / "02-System" / "ARCHITECTURE.md"
    assert arch_link.is_symlink()
    assert arch_link.resolve() == (root / "docs" / "architecture.md").resolve()

    # Source untouched: porcelain shows NO modified/deleted/renamed TRACKED file outside `.claude/`.
    # Untracked additions (`??` — the new symlink + `.claude/`) are sanctioned per AC6.
    porcelain = _git(["status", "--porcelain"], root).stdout
    mutated = [
        line[3:]
        for line in porcelain.splitlines()
        if line.strip() and not line.startswith("??") and not line[3:].startswith(".claude/")
    ]
    assert mutated == [], f"adopt mutated tracked source files: {mutated}"
