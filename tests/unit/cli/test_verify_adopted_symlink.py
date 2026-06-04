"""Verify allows known-adopted leaf symlinks (Story 3.4, AC4)."""

from __future__ import annotations

import json
import os
import sys
import unicodedata
import unittest.mock
from pathlib import Path

import pytest
from typer.testing import CliRunner

if sys.platform == "win32":
    pytest.skip("POSIX-only", allow_module_level=True)

from sdlc.cli.main import app
from sdlc.contracts.adopted_symlinks import AdoptedSymlinks, SymlinkMapping

pytestmark = pytest.mark.unit
_runner = CliRunner()
_ARTIFACT = "01-Requirement/01-PRODUCT.md"
_MANIFEST = ".claude/state/adopted-symlinks.json"


def _bootstrap(tmp_path: Path, *, adopted: bool) -> None:
    state = tmp_path / ".claude" / "state"
    state.mkdir(parents=True)
    (state / "state.json").write_text(
        '{"schema_version":1,"next_monotonic_seq":0,"phase":1,'
        '"epics":{},"stories":{},"tasks":{}}\n',
        encoding="utf-8",
    )
    (state / "journal.log").touch()
    src = tmp_path / "legacy" / "product.md"
    src.parent.mkdir(parents=True)
    src.write_text("# Product\n", encoding="utf-8")
    target = tmp_path / _ARTIFACT
    target.parent.mkdir(parents=True)
    os.symlink(os.path.relpath(src, target.parent), target)
    if adopted:
        mapping = SymlinkMapping(
            source="legacy/product.md",
            target=_ARTIFACT,
            accepted_at="2026-06-04T12:00:00.000Z",
            kind="prd",
        )
        text = json.dumps(
            AdoptedSymlinks(mappings=(mapping,)).model_dump(mode="json"),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        (state / "adopted-symlinks.json").write_bytes(
            (unicodedata.normalize("NFC", text) + "\n").encode("utf-8")
        )


def test_adopted_leaf_symlink_reaches_dispatch(tmp_path: Path) -> None:
    _bootstrap(tmp_path, adopted=True)
    reached: list[str] = []

    def _dispatch(**kwargs: object) -> None:
        reached.append(str(kwargs.get("artifact_id")))

    with (
        unittest.mock.patch("sdlc.cli.verify._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch("sdlc.cli.verify._invoke_dispatch", side_effect=_dispatch),
    ):
        result = _runner.invoke(app, ["verify", _ARTIFACT])
    assert result.exit_code == 0
    assert reached == [_ARTIFACT]


def test_unknown_symlink_still_rejected(tmp_path: Path) -> None:
    _bootstrap(tmp_path, adopted=False)
    with (
        unittest.mock.patch("sdlc.cli.verify._get_repo_root_or_cwd", return_value=tmp_path),
        unittest.mock.patch(
            "sdlc.cli.verify._invoke_dispatch",
            side_effect=AssertionError("must not dispatch"),
        ),
    ):
        result = _runner.invoke(app, ["verify", _ARTIFACT])
    assert result.exit_code != 0
    out = result.stderr + result.stdout
    # P11: assert the SPECIFIC ancestor-symlink guard fired (not merely any ERR_PATH_TRAVERSAL,
    # which the resolved-containment/source-binding branches also emit).
    assert "symlink component" in out


def test_build_idea_with_origin_injects_block_when_sidecar_present(tmp_path: Path) -> None:
    """AC4(ii): an imported-metadata sidecar makes verify prepend the <IMPORTED_ORIGIN> block."""
    from sdlc.adopt.imported_metadata import (
        ImportedMetadataRecord,
        metadata_record_path,
        record_to_yaml_bytes,
    )
    from sdlc.cli._verify_dispatch import _build_idea_with_origin

    target = _ARTIFACT
    record = ImportedMetadataRecord(
        source="legacy/product.md",
        target=target,
        kind="prd",  # type: ignore[arg-type]
        imported_at="2026-06-04T12:00:00.000Z",
        frontmatter=None,
    )
    record_path = metadata_record_path(tmp_path, target)
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_bytes(record_to_yaml_bytes(record))

    idea = _build_idea_with_origin(tmp_path, target, "ARTIFACT BODY")
    assert "<IMPORTED_ORIGIN>" in idea
    assert "Source path: legacy/product.md" in idea
    assert "Canonical target: " + target in idea
    assert idea.endswith("ARTIFACT BODY")


def test_build_idea_with_origin_passthrough_when_no_sidecar(tmp_path: Path) -> None:
    """A non-adopted artifact (no sidecar) is dispatched verbatim — no origin block."""
    from sdlc.cli._verify_dispatch import _build_idea_with_origin

    assert _build_idea_with_origin(tmp_path, _ARTIFACT, "BODY") == "BODY"
