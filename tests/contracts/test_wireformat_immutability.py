"""Wire-format immutability gate (Story 1.21, Decision F3, Architecture §382 + §1238).

Fails if any of the 5 wire-format pydantic contracts has its JSON-Schema diverge
from the committed snapshot at tests/contract_snapshots/v1/<slug>.json. The diff
names the contract, the field that changed, and the required action: bump
schema_version + add migration + regenerate the snapshot via
scripts/freeze_wireformat_snapshots.py --write.

This test IS the lock ceremony — its presence + green status is the load-bearing
property of Decision F3 + the Epic 2A entry gate.
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Final

import pytest
from pydantic import BaseModel

from sdlc.contracts import (
    HookPayload,
    JournalEntry,
    ResumeToken,
    SpecialistFrontmatter,
    WorkflowSpec,
)

pytestmark = pytest.mark.unit

_SNAPSHOT_DIR: Final[Path] = Path(__file__).parent.parent / "contract_snapshots" / "v1"

# Duplicate of scripts/freeze_wireformat_snapshots.py:_CONTRACTS — intentional.
# Tests must not depend on scripts/; Test C below cross-checks parity between the two.
_CONTRACTS: Final[tuple[tuple[str, type[BaseModel]], ...]] = (
    ("journal_entry", JournalEntry),
    ("resume_token", ResumeToken),
    ("hook_payload", HookPayload),
    ("specialist_frontmatter", SpecialistFrontmatter),
    ("workflow_spec", WorkflowSpec),
)

_DIFF_MAX_LINES: Final[int] = 80


def _canonical_schema_bytes(model_cls: type[BaseModel]) -> bytes:
    schema_dict = model_cls.model_json_schema(mode="serialization")
    return (
        json.dumps(
            schema_dict,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            indent=2,
        ).encode("utf-8")
        + b"\n"
    )


def _unified_diff(a: bytes, b: bytes, label: str) -> str:
    a_lines = a.decode("utf-8", errors="replace").splitlines(keepends=True)
    b_lines = b.decode("utf-8", errors="replace").splitlines(keepends=True)
    diff_lines = list(difflib.unified_diff(a_lines, b_lines, fromfile=label, tofile="<live>"))
    if len(diff_lines) > _DIFF_MAX_LINES:
        diff_lines = [*diff_lines[:_DIFF_MAX_LINES], "... [truncated]\n"]
    return "".join(diff_lines)


@pytest.mark.unit
@pytest.mark.parametrize("slug,model_cls", _CONTRACTS, ids=[s for s, _ in _CONTRACTS])
def test_wireformat_schema_matches_snapshot(slug: str, model_cls: type[BaseModel]) -> None:
    snapshot_path = _SNAPSHOT_DIR / f"{slug}.json"
    assert snapshot_path.exists(), (
        f"missing snapshot: {snapshot_path}\n"
        f"action: run `uv run python scripts/freeze_wireformat_snapshots.py --write` "
        f"to bootstrap, then commit."
    )
    snapshot_bytes = snapshot_path.read_bytes()
    live_bytes = _canonical_schema_bytes(model_cls)
    assert live_bytes == snapshot_bytes, (
        f"wireformat-immutability drift: {model_cls.__name__} schema diverged from "
        f"snapshot at {snapshot_path}\n"
        f"action: bump {model_cls.__name__}.schema_version (Literal[1] -> Literal[2]) "
        f"AND add migration entry under src/sdlc/migrations/contracts/v<N>.py "
        f"(see ADR-024), THEN run "
        f"`uv run python scripts/freeze_wireformat_snapshots.py --write`.\n"
        f"--- diff (first {_DIFF_MAX_LINES} lines): ---\n"
        f"{_unified_diff(snapshot_bytes, live_bytes, str(snapshot_path))}"
    )


@pytest.mark.unit
def test_contracts_tuple_matches_public_all() -> None:
    """Guard against silent contract drift: the locked set MUST equal sdlc.contracts.__all__."""
    import sdlc.contracts

    locked_class_names = frozenset(cls.__name__ for _, cls in _CONTRACTS)
    public_class_names = frozenset(sdlc.contracts.__all__)
    assert locked_class_names == public_class_names, (
        f"wireformat-immutability registry drift:\n"
        f"  locked but not public: {locked_class_names - public_class_names}\n"
        f"  public but not locked: {public_class_names - locked_class_names}\n"
        f"action: if you intentionally added a 6th wire-format contract, append it to "
        f"_CONTRACTS in BOTH scripts/freeze_wireformat_snapshots.py AND "
        f"tests/contracts/test_wireformat_immutability.py, run --write, commit the new "
        f"snapshot, AND amend ADR-024 with the new contract."
    )


@pytest.mark.unit
def test_script_and_test_share_contract_registry() -> None:
    """Guard against script vs test _CONTRACTS drift."""
    # scripts/ is on sys.path via tests/conftest.py (Story 1.4 / Story 1.21)
    import freeze_wireformat_snapshots  # type: ignore[import-not-found]

    script_slugs = tuple(slug for slug, _ in freeze_wireformat_snapshots._CONTRACTS)
    test_slugs = tuple(slug for slug, _ in _CONTRACTS)
    assert script_slugs == test_slugs, (
        f"script vs test contract list drift:\n"
        f"  script: {script_slugs}\n"
        f"  test:   {test_slugs}\n"
        f"action: keep _CONTRACTS in lockstep across both files."
    )
    script_classes = tuple(cls for _, cls in freeze_wireformat_snapshots._CONTRACTS)
    test_classes = tuple(cls for _, cls in _CONTRACTS)
    assert script_classes == test_classes, (
        "script vs test contract class list drift; same actions as above."
    )
