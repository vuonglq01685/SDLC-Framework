"""Generate / verify the pinned JSON-Schema snapshot of each wire-format contract
(Story 1.21, Decision F3).

Produces tests/contract_snapshots/v{N}/<contract>.json — one file per contract per
schema version. The bytes are deterministic: pydantic JSON Schema in serialization
mode, then canonicalized via the same NFC + sort_keys + (',', ':') separators rule
used by sdlc.journal._canonical (Architecture §501-§508), terminated with a single
trailing '\\n'.

Default mode (no flags): VERIFY — load each snapshot, regenerate live, assert bytes
equal. Exit 0 on match, exit 1 on drift naming the offending contract + path.
--write mode: regenerate snapshots in place. Reserved for the dev who is
intentionally bumping a schema_version + authoring the migration. CI MUST NEVER
run --write.

Note: mode="serialization" is chosen deliberately (not mode="validation"). The wire
format is what comes OUT of model_dump(mode="json") — the bytes that hit disk and
cross process boundaries. Decision F3's "wire-format contract" is the SERIALIZATION
shape. See ADR-024 for full rationale.

state.schema_version (src/sdlc/state/model.py) is NOT one of the 5 wire-format
contracts — it is a process-internal projection (Decision B5) locked separately by
Story 1.19's migration discipline (src/sdlc/state/reader.py:CURRENT_SCHEMA_VERSION).
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from pydantic import BaseModel

from sdlc.contracts import (
    HookPayload,
    JournalEntry,
    ResumeToken,
    SpecialistFrontmatter,
    WorkflowSpec,
)

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
_SNAPSHOT_DIR: Final[Path] = _REPO_ROOT / "tests" / "contract_snapshots" / "v1"
_DIFF_MAX_LINES: Final[int] = 80

# Canonical iteration order — referenced by AC2's test, AC4's CI step, and ADR-024.
# ANY change to this list (add a 6th contract, rename a slug) is a wire-format-surface
# change requiring an ADR amendment + new snapshot file.
_CONTRACTS: Final[tuple[tuple[str, type[BaseModel]], ...]] = (
    ("journal_entry", JournalEntry),
    ("resume_token", ResumeToken),
    ("hook_payload", HookPayload),
    ("specialist_frontmatter", SpecialistFrontmatter),
    ("workflow_spec", WorkflowSpec),
)


def _snapshot_path(repo_root: Path, slug: str, version: int) -> Path:
    return repo_root / "tests" / "contract_snapshots" / f"v{version}" / f"{slug}.json"


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


def _verify_one(slug: str, model_cls: type[BaseModel], path: Path) -> tuple[bool, str | None]:
    snapshot_bytes = path.read_bytes()
    live_bytes = _canonical_schema_bytes(model_cls)
    if live_bytes == snapshot_bytes:
        return True, None
    diff = _unified_diff(snapshot_bytes, live_bytes, str(path))
    msg = (
        f"wireformat-immutability drift: {slug} schema mismatch at {path}\n"
        f"   action: bump {model_cls.__name__}.schema_version + add migration; "
        f"then run scripts/freeze_wireformat_snapshots.py --write\n"
        f"--- diff (first {_DIFF_MAX_LINES} lines): ---\n{diff}"
    )
    return False, msg


def _write_one(slug: str, model_cls: type[BaseModel], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_schema_bytes(model_cls))


def _run_write(repo_root: Path, yes: bool, is_tty: bool) -> int:
    if is_tty and not yes:
        answer = input(
            f"about to overwrite {len(_CONTRACTS)} snapshot files in "
            f"tests/contract_snapshots/v1/. Proceed? [y/N]: "
        )
        if answer.strip().lower() != "y":
            print("Aborted.", file=sys.stderr)
            return 1
    for slug, model_cls in _CONTRACTS:
        path = _snapshot_path(repo_root, slug, 1)
        _write_one(slug, model_cls, path)
    print(
        f"wireformat-immutability write: {len(_CONTRACTS)} snapshots written to "
        f"tests/contract_snapshots/v1/"
    )
    return 0


def _run_check(repo_root: Path) -> int:
    all_ok = True
    for slug, model_cls in _CONTRACTS:
        path = _snapshot_path(repo_root, slug, 1)
        if not path.exists():
            print(
                f"wireformat-immutability bootstrap failure: snapshot file missing at {path}\n"
                f"   action: run scripts/freeze_wireformat_snapshots.py --write "
                f"to generate the v1 baseline",
                file=sys.stderr,
            )
            return 2
        ok, msg = _verify_one(slug, model_cls, path)
        if not ok:
            print(msg, file=sys.stderr)
            all_ok = False

    if all_ok:
        print(
            f"wireformat-immutability check: {len(_CONTRACTS)} contracts match snapshots at "
            f"tests/contract_snapshots/v1/"
        )
        return 0
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Verify or regenerate wire-format contract snapshots.

    CI MUST NEVER run --write. Default mode is verify (--check).
    --write is reserved for devs intentionally bumping a schema_version + migration.
    --yes suppresses the interactive confirmation prompt (non-interactive contexts).
    """
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser(
        description="Verify or regenerate wire-format contract snapshots.",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--check", action="store_true", help="Verify snapshots (default).")
    mode_group.add_argument("--write", action="store_true", help="Regenerate snapshots in place.")
    parser.add_argument(
        "--yes", action="store_true", help="Skip interactive confirmation for --write."
    )
    args = parser.parse_args(list(argv))

    if args.write:
        return _run_write(_REPO_ROOT, args.yes, sys.stdin.isatty())
    return _run_check(_REPO_ROOT)


if __name__ == "__main__":
    sys.exit(main())
