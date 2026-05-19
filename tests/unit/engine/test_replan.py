"""Unit tests for engine/replan.py (Story 2A.19, Task 2.1).

Tests:
  - resolve_scope_phase: 01-/02-/03- prefixes → 1/2/3; unknown → raises WorkflowError
  - compute_downstream: scope_phase=1 → files under 02- + 03-; =2 → under 03-; =3 → empty
  - plan_invalidations: only APPROVED phases >= scope_phase in {1,2}; already-invalidated excluded
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# resolve_scope_phase
# ---------------------------------------------------------------------------


def test_resolve_scope_phase_01() -> None:
    from sdlc.engine.replan import resolve_scope_phase

    assert resolve_scope_phase("01-Requirement/01-PRODUCT.md") == 1


def test_resolve_scope_phase_02() -> None:
    from sdlc.engine.replan import resolve_scope_phase

    assert resolve_scope_phase("02-Architecture/02-System/ARCHITECTURE.md") == 2


def test_resolve_scope_phase_03() -> None:
    from sdlc.engine.replan import resolve_scope_phase

    assert resolve_scope_phase("03-Implementation/some-file.py") == 3


def test_resolve_scope_phase_nested_01() -> None:
    from sdlc.engine.replan import resolve_scope_phase

    assert resolve_scope_phase("01-Requirement/sub/deep/doc.md") == 1


def test_resolve_scope_phase_unknown_raises() -> None:
    from sdlc.engine.replan import resolve_scope_phase
    from sdlc.errors.base import WorkflowError

    with pytest.raises(WorkflowError, match="not under a recognized phase directory"):
        resolve_scope_phase("04-Unknown/artifact.md")


def test_resolve_scope_phase_docs_raises() -> None:
    from sdlc.engine.replan import resolve_scope_phase
    from sdlc.errors.base import WorkflowError

    with pytest.raises(WorkflowError):
        resolve_scope_phase("docs/ADR-001.md")


# ---------------------------------------------------------------------------
# compute_downstream
# ---------------------------------------------------------------------------


def test_compute_downstream_phase1_covers_02_and_03(tmp_path: Path) -> None:
    """scope_phase=1 → everything under 02- and 03- directories."""
    from sdlc.engine.replan import compute_downstream

    # Seed some files
    (tmp_path / "01-Requirement").mkdir()
    (tmp_path / "01-Requirement" / "PRODUCT.md").write_text("p1\n", encoding="utf-8")
    arch_dir = tmp_path / "02-Architecture" / "02-System"
    arch_dir.mkdir(parents=True)
    (arch_dir / "ARCHITECTURE.md").write_text("arch\n", encoding="utf-8")
    impl_dir = tmp_path / "03-Implementation"
    impl_dir.mkdir()
    (impl_dir / "code.py").write_text("pass\n", encoding="utf-8")

    downstream, count = compute_downstream(tmp_path, 1)

    # Must include 02- and 03- files, not 01-
    downstream_set = set(downstream)
    assert "02-Architecture/02-System/ARCHITECTURE.md" in downstream_set
    assert "03-Implementation/code.py" in downstream_set
    assert not any(p.startswith("01-") for p in downstream_set)
    assert count == len(downstream)


def test_compute_downstream_phase2_covers_only_03(tmp_path: Path) -> None:
    """scope_phase=2 → only files under 03-Implementation."""
    from sdlc.engine.replan import compute_downstream

    arch_dir = tmp_path / "02-Architecture"
    arch_dir.mkdir()
    (arch_dir / "doc.md").write_text("arch\n", encoding="utf-8")
    impl_dir = tmp_path / "03-Implementation"
    impl_dir.mkdir()
    (impl_dir / "code.py").write_text("pass\n", encoding="utf-8")

    downstream, count = compute_downstream(tmp_path, 2)

    downstream_set = set(downstream)
    assert "03-Implementation/code.py" in downstream_set
    assert not any(p.startswith("02-") for p in downstream_set)
    assert count == 1


def test_compute_downstream_phase3_empty(tmp_path: Path) -> None:
    """scope_phase=3 → no downstream phases."""
    from sdlc.engine.replan import compute_downstream

    impl_dir = tmp_path / "03-Implementation"
    impl_dir.mkdir()
    (impl_dir / "code.py").write_text("pass\n", encoding="utf-8")

    downstream, count = compute_downstream(tmp_path, 3)
    assert downstream == []
    assert count == 0


def test_compute_downstream_count_matches_list(tmp_path: Path) -> None:
    """Returned count always equals len(downstream)."""
    from sdlc.engine.replan import compute_downstream

    arch_dir = tmp_path / "02-Architecture"
    arch_dir.mkdir()
    for i in range(3):
        (arch_dir / f"doc{i}.md").write_text(f"doc{i}\n", encoding="utf-8")
    impl_dir = tmp_path / "03-Implementation"
    impl_dir.mkdir()
    (impl_dir / "code.py").write_text("pass\n", encoding="utf-8")

    downstream, count = compute_downstream(tmp_path, 1)
    assert count == len(downstream)


def test_compute_downstream_missing_phase_dir(tmp_path: Path) -> None:
    """If downstream phase directory does not exist, it's silently skipped."""
    from sdlc.engine.replan import compute_downstream

    # No 03-Implementation directory exists
    (tmp_path / "02-Architecture").mkdir()
    (tmp_path / "02-Architecture" / "arch.md").write_text("arch\n", encoding="utf-8")

    downstream, count = compute_downstream(tmp_path, 2)
    # No 03- dir → empty
    assert downstream == []
    assert count == 0


# ---------------------------------------------------------------------------
# plan_invalidations
# ---------------------------------------------------------------------------


def _init_repo(tmp_path: Path) -> None:
    import unittest.mock

    import typer

    from sdlc.cli import init as init_mod

    ctx = typer.Context(command=typer.core.TyperCommand("init"))
    ctx.ensure_object(dict)
    with unittest.mock.patch.object(init_mod, "_get_repo_root_or_cwd", return_value=tmp_path):
        init_mod.run_init(ctx=ctx)


def _approve_phase(tmp_path: Path, phase: int, artifact_rel: str) -> None:
    from sdlc.signoff import ArtifactRef, SignoffRecord, write_record
    from sdlc.signoff.hasher import compute_artifact_hash

    artifact_path = tmp_path / artifact_rel
    artifact_hash = compute_artifact_hash(artifact_path, repo_root=tmp_path)
    record = SignoffRecord(
        phase=phase,
        artifacts=(ArtifactRef(path=artifact_rel, hash=artifact_hash),),
        approved_by="test-approver",
        approved_at="2026-05-19T10:00:00.000Z",
        drafted_at="2026-05-19T09:00:00.000Z",
        validated_at="2026-05-19T10:00:00.000Z",
    )
    write_record(record, repo_root=tmp_path)


def test_plan_invalidations_phase2_scope_both_approved(tmp_path: Path) -> None:
    """scope_phase=2, both P1 and P2 APPROVED → only P2 returned."""
    from sdlc.engine.replan import plan_invalidations

    product_rel = "01-Requirement/PRODUCT.md"
    arch_rel = "02-Architecture/ARCH.md"
    _init_repo(tmp_path)
    (tmp_path / "01-Requirement").mkdir(parents=True, exist_ok=True)
    (tmp_path / product_rel).write_text("product\n", encoding="utf-8")
    (tmp_path / "02-Architecture").mkdir(parents=True, exist_ok=True)
    (tmp_path / arch_rel).write_text("arch\n", encoding="utf-8")
    _approve_phase(tmp_path, 1, product_rel)
    _approve_phase(tmp_path, 2, arch_rel)

    phases = plan_invalidations(tmp_path, 2)
    assert phases == [2]


def test_plan_invalidations_phase1_scope_both_approved(tmp_path: Path) -> None:
    """scope_phase=1, both P1 and P2 APPROVED → both returned."""
    from sdlc.engine.replan import plan_invalidations

    product_rel = "01-Requirement/PRODUCT.md"
    arch_rel = "02-Architecture/ARCH.md"
    _init_repo(tmp_path)
    (tmp_path / "01-Requirement").mkdir(parents=True, exist_ok=True)
    (tmp_path / product_rel).write_text("product\n", encoding="utf-8")
    (tmp_path / "02-Architecture").mkdir(parents=True, exist_ok=True)
    (tmp_path / arch_rel).write_text("arch\n", encoding="utf-8")
    _approve_phase(tmp_path, 1, product_rel)
    _approve_phase(tmp_path, 2, arch_rel)

    phases = plan_invalidations(tmp_path, 1)
    assert phases == [1, 2]


def test_plan_invalidations_phase3_scope_returns_empty(tmp_path: Path) -> None:
    """scope_phase=3 → no phases in {1,2} satisfy >= 3, so empty list."""
    from sdlc.engine.replan import plan_invalidations

    _init_repo(tmp_path)
    phases = plan_invalidations(tmp_path, 3)
    assert phases == []


def test_plan_invalidations_already_invalidated_excluded(tmp_path: Path) -> None:
    """Already-invalidated phase is not in the returned list (replan-then-replan guard)."""
    from sdlc.engine.replan import plan_invalidations
    from sdlc.signoff.records import invalidate_record

    arch_rel = "02-Architecture/ARCH.md"
    _init_repo(tmp_path)
    (tmp_path / "02-Architecture").mkdir(parents=True, exist_ok=True)
    (tmp_path / arch_rel).write_text("arch\n", encoding="utf-8")
    _approve_phase(tmp_path, 2, arch_rel)

    # First invalidation
    invalidate_record(2, repo_root=tmp_path, reason="test", now_utc="2026-05-19T10:00:00.000Z")

    # Now plan_invalidations should not include phase 2
    phases = plan_invalidations(tmp_path, 2)
    assert 2 not in phases


def test_plan_invalidations_no_signoff_returns_empty(tmp_path: Path) -> None:
    """Phases with no signoff record are excluded (not APPROVED)."""
    from sdlc.engine.replan import plan_invalidations

    _init_repo(tmp_path)
    phases = plan_invalidations(tmp_path, 1)
    assert phases == []
