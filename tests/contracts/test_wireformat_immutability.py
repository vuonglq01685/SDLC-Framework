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

# Single source of truth (Story 1.21 review patch P20): the registry lives in
# sdlc.contracts. The previous "test C parity" assertion is no longer needed —
# script and test now share the same import.
from sdlc.contracts import _WIRE_FORMAT_REGISTRY

# Module-level pytestmark applies to every test below; per-test @pytest.mark.unit
# decorators dropped as redundant (P18).
pytestmark = pytest.mark.unit

_SNAPSHOT_DIR: Final[Path] = Path(__file__).parent.parent / "contract_snapshots" / "v1"
_DIFF_MAX_LINES: Final[int] = 80

_CONTRACTS: Final[tuple[tuple[str, type[BaseModel]], ...]] = _WIRE_FORMAT_REGISTRY


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
    # errors="strict" surfaces real corruption instead of silently substituting
    # U+FFFD; truncate to (_DIFF_MAX_LINES - 1) so the marker doesn't replace the
    # last real diff line at the threshold boundary.
    try:
        a_lines = a.decode("utf-8").splitlines(keepends=True)
        b_lines = b.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError as exc:
        return (
            f"--- diff unavailable: snapshot encoding corrupt ({exc}). "
            f"Run scripts/freeze_wireformat_snapshots.py --write to repair.\n"
        )
    diff_lines = list(difflib.unified_diff(a_lines, b_lines, fromfile=label, tofile="<live>"))
    if len(diff_lines) > _DIFF_MAX_LINES:
        diff_lines = [*diff_lines[: _DIFF_MAX_LINES - 1], "... [truncated]\n"]
    return "".join(diff_lines)


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
        # P6: per-slug subdir form matches Forward-Compat Seam #2 + ADR-024 §3.
        f"action: bump {model_cls.__name__}.schema_version (Literal[1] -> Literal[2]) "
        f"AND add migration entry under src/sdlc/migrations/contracts/v<N>/{slug}.py "
        f"(see ADR-024), THEN run "
        f"`uv run python scripts/freeze_wireformat_snapshots.py --write`.\n"
        f"--- diff (first {_DIFF_MAX_LINES} lines): ---\n"
        f"{_unified_diff(snapshot_bytes, live_bytes, str(snapshot_path))}"
    )


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
        f"_WIRE_FORMAT_REGISTRY in src/sdlc/contracts/__init__.py, run "
        f"`scripts/freeze_wireformat_snapshots.py --write`, commit the new snapshot, "
        f"AND amend ADR-024 with the new contract."
    )


# P15: defensive uniqueness assertions on the registry. The script also asserts these
# at module-load time; this test ensures pytest catches a duplicate slug/class even if
# someone runs the script with assertions disabled (`python -O`).
def test_wire_format_registry_has_unique_slugs() -> None:
    slugs = [slug for slug, _ in _CONTRACTS]
    assert len(set(slugs)) == len(slugs), f"duplicate slugs in _WIRE_FORMAT_REGISTRY: {slugs}"


def test_wire_format_registry_has_unique_classes() -> None:
    classes = [cls for _, cls in _CONTRACTS]
    assert len(set(classes)) == len(classes), (
        f"duplicate classes in _WIRE_FORMAT_REGISTRY: {[c.__name__ for c in classes]}"
    )
