"""Unit tests for `sdlc adopt-rollback` CLI (Story 3.5)."""

from __future__ import annotations

import os
import sys
import unittest.mock
from pathlib import Path

import pytest

if sys.platform == "win32":  # pragma: no cover
    pytest.skip("adopt mode is POSIX-only in v1", allow_module_level=True)

from typer.testing import CliRunner

from sdlc.contracts.adopted_symlinks import AdoptedSymlinks, SymlinkMapping
from unit.adopt._symlink_offer_common import ARCH_TARGET, JOURNAL_REL, MANIFEST_REL, journal_entries

pytestmark = pytest.mark.unit

_runner = CliRunner()
_TS = "2026-06-04T12:00:00.000Z"
_VALID_HASH = "sha256:" + "a" * 64
_TS1 = "2026-01-01T00:00:00.000Z"
_TS2 = "2026-01-02T00:00:00.000Z"
_TS3 = "2026-01-03T00:00:00.000Z"
_PHASE_DIR = {2: "02-Architecture"}
_ORPHAN_MSG = "rollback would orphan signoff phase-2; replan first or use --force"


def _invoke_rollback(
    root: Path,
    *,
    sub_flags: tuple[str, ...] = (),
    global_flags: tuple[str, ...] = (),
) -> object:
    from sdlc.cli.main import app

    args = [*global_flags, "adopt-rollback", *sub_flags]
    with unittest.mock.patch("sdlc.cli.adopt_rollback._get_repo_root_or_cwd", return_value=root):
        return _runner.invoke(app, args)


def _scaffold_cli(root: Path) -> None:
    state = root / ".claude" / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "state.json").write_text("{}", encoding="utf-8")
    (state / "journal.log").touch()
    (state / "signoffs").mkdir(parents=True, exist_ok=True)


def _write_manifest(root: Path, mappings: list[SymlinkMapping]) -> None:
    path = root / MANIFEST_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        AdoptedSymlinks(mappings=tuple(mappings)).model_dump_json() + "\n",
        encoding="utf-8",
    )


def _link(root: Path, source_rel: str, target_rel: str) -> None:
    src = root / source_rel
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("# src\n", encoding="utf-8")
    slot = root / target_rel
    slot.parent.mkdir(parents=True, exist_ok=True)
    if slot.exists() or slot.is_symlink():
        slot.unlink()
    rel = os.path.relpath(src.resolve(), slot.parent.resolve())
    os.symlink(rel, slot)


def _write_approved_phase2_signoff(repo_root: Path) -> None:
    from sdlc.signoff.records import ArtifactRef, SignoffRecord, write_record

    record = SignoffRecord(
        phase=2,
        artifacts=(ArtifactRef(path=f"{_PHASE_DIR[2]}/PRODUCT.md", hash=_VALID_HASH),),
        approved_by="alice",
        approved_at=_TS2,
        drafted_at=_TS1,
        validated_at=_TS3,
        invalidated_at=None,
    )
    write_record(record, repo_root=repo_root)


def test_orphan_signoff_refuses_without_force_no_mutation(tmp_path: Path) -> None:
    root = tmp_path
    _scaffold_cli(root)
    _write_approved_phase2_signoff(root)
    _write_manifest(
        root,
        [
            SymlinkMapping(
                source="docs/architecture-2024.md",
                target=ARCH_TARGET,
                accepted_at=_TS,
                kind="architecture",
            )
        ],
    )
    _link(root, "docs/architecture-2024.md", ARCH_TARGET)
    manifest_before = (root / MANIFEST_REL).read_bytes()
    journal_before = (root / JOURNAL_REL).read_bytes()
    signoff_before = (root / ".claude" / "state" / "signoffs" / "phase-2.yaml").read_bytes()

    result = _invoke_rollback(root, sub_flags=("--target", ARCH_TARGET))
    assert result.exit_code == 2, result.output
    assert _ORPHAN_MSG in result.output
    assert (root / MANIFEST_REL).read_bytes() == manifest_before
    assert (root / JOURNAL_REL).read_bytes() == journal_before
    assert (root / ARCH_TARGET).is_symlink()
    assert (root / ".claude" / "state" / "signoffs" / "phase-2.yaml").read_bytes() == signoff_before


def test_force_invalidates_signoff_and_rolls_back(tmp_path: Path) -> None:
    root = tmp_path
    _scaffold_cli(root)
    _write_approved_phase2_signoff(root)
    _write_manifest(
        root,
        [
            SymlinkMapping(
                source="docs/architecture-2024.md",
                target=ARCH_TARGET,
                accepted_at=_TS,
                kind="architecture",
            )
        ],
    )
    _link(root, "docs/architecture-2024.md", ARCH_TARGET)

    result = _invoke_rollback(root, sub_flags=("--target", ARCH_TARGET, "--force"))
    assert result.exit_code == 0, result.output
    assert not (root / ARCH_TARGET).exists()
    signoff_text = (root / ".claude" / "state" / "signoffs" / "phase-2.yaml").read_text(
        encoding="utf-8"
    )
    assert "invalidated_at:" in signoff_text
    kinds = [e.kind for e in journal_entries(root)]
    assert "adopt_rollback_started" in kinds
    assert "signoff_invalidated" in kinds
    assert "symlink_rolled_back" in kinds
    # The intent anchor is journaled BEFORE the destructive invalidation (fail-loud posture).
    assert kinds.index("adopt_rollback_started") < kinds.index("signoff_invalidated")


def test_target_outside_phase_proceeds_without_orphan_check(tmp_path: Path) -> None:
    root = tmp_path
    _scaffold_cli(root)
    outside = "docs/standalone.md"
    _write_manifest(
        root,
        [
            SymlinkMapping(
                source="docs/src.md",
                target=outside,
                accepted_at=_TS,
                kind="readme",
            )
        ],
    )
    _link(root, "docs/src.md", outside)

    result = _invoke_rollback(root, sub_flags=("--target", outside))
    assert result.exit_code == 0, result.output
    assert not (root / outside).exists()
    manifest = AdoptedSymlinks.model_validate_json(
        (root / MANIFEST_REL).read_text(encoding="utf-8")
    )
    assert manifest.mappings == ()
