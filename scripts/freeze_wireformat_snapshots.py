"""Generate / verify the pinned JSON-Schema snapshot of each wire-format contract
(Story 1.21, Decision F3).

Produces tests/contract_snapshots/v{N}/<contract>.json — one file per contract per
schema version. The bytes are deterministic:

    json.dumps(
        model_cls.model_json_schema(mode="serialization"),
        sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), indent=2,
    ).encode("utf-8") + b"\\n"

Distinct from sdlc.journal._canonical's compact form (no indent, NFC-normalised).
See ADR-024 for the indent=2 rationale (PR-diff legibility outweighs strict
on-the-wire compactness for dev-time fixtures).

Default mode (no flags): VERIFY — load each snapshot, regenerate live, assert bytes
equal. Exit 0 on match, exit 1 on drift, exit 2 on missing-snapshot bootstrap
failure or refused non-tty --write, exit 3 on user abort at interactive prompt.
--write mode: regenerate snapshots in place. Reserved for the dev who is
intentionally bumping a schema_version + authoring the migration. CI MUST NEVER
run --write. Non-tty invocation refuses without --yes (silent overwrite is a
foot-gun).

Note: mode="serialization" is chosen deliberately (not mode="validation"). The wire
format is what comes OUT of model_dump(mode="json") — the bytes that hit disk and
cross process boundaries. Decision F3's "wire-format contract" is the SERIALIZATION
shape. See ADR-024 for full rationale.

state.schema_version (src/sdlc/state/model.py) is NOT one of the 5 wire-format
contracts — it is a process-internal projection (Decision B5) locked separately by
Story 1.19's migration discipline (src/sdlc/state/reader.py:CURRENT_SCHEMA_VERSION).

Exit codes:
  0  match (or successful --write)
  1  drift detected (verify failure — bump schema_version + add migration)
  2  framework / setup error (snapshot file missing, refused non-tty --write,
     ambiguous flag combination)
  3  user aborted at interactive prompt (or EOF on stdin)
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from pydantic import BaseModel

from sdlc.contracts import _WIRE_FORMAT_REGISTRY

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
_SNAPSHOT_DIR: Final[Path] = _REPO_ROOT / "tests" / "contract_snapshots" / "v1"
_DIFF_MAX_LINES: Final[int] = 80

# Exit codes (see module docstring).
_EXIT_OK: Final[int] = 0
_EXIT_DRIFT: Final[int] = 1
_EXIT_FRAMEWORK: Final[int] = 2
_EXIT_USER_ABORT: Final[int] = 3

# Local alias for legibility; the canonical source is sdlc.contracts._WIRE_FORMAT_REGISTRY.
# Adding a 6th contract requires an ADR amendment + new snapshot file (and is rejected
# at module-load time by the uniqueness asserts below).
_CONTRACTS: Final[tuple[tuple[str, type[BaseModel]], ...]] = _WIRE_FORMAT_REGISTRY

# Defensive registry invariants (P15): catch slug or class duplication at import time
# rather than letting one snapshot silently overwrite another during --write.
assert len({slug for slug, _ in _CONTRACTS}) == len(_CONTRACTS), (
    f"_WIRE_FORMAT_REGISTRY has duplicate slugs: {[s for s, _ in _CONTRACTS]}"
)
assert len({cls for _, cls in _CONTRACTS}) == len(_CONTRACTS), (
    f"_WIRE_FORMAT_REGISTRY has duplicate classes: {[c.__name__ for _, c in _CONTRACTS]}"
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
    # errors="strict" surfaces real corruption (UTF-16 BOM'd file, mojibake) instead
    # of silently substituting U+FFFD and producing a misleading "looks-like-text" diff.
    try:
        a_lines = a.decode("utf-8").splitlines(keepends=True)
        b_lines = b.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError as exc:
        return (
            f"--- diff unavailable: snapshot encoding corrupt ({exc}). "
            f"Run scripts/freeze_wireformat_snapshots.py --write to repair.\n"
        )
    diff_lines = list(difflib.unified_diff(a_lines, b_lines, fromfile=label, tofile="<live>"))
    # Truncate to (_DIFF_MAX_LINES - 1) so the marker doesn't replace the last real
    # diff line at the threshold boundary.
    if len(diff_lines) > _DIFF_MAX_LINES:
        diff_lines = [*diff_lines[: _DIFF_MAX_LINES - 1], "... [truncated]\n"]
    return "".join(diff_lines)


def _verify_one(slug: str, model_cls: type[BaseModel], path: Path) -> tuple[bool, str | None]:
    snapshot_bytes = path.read_bytes()
    live_bytes = _canonical_schema_bytes(model_cls)
    if live_bytes == snapshot_bytes:
        return True, None
    # Surface empty / corrupt snapshot before computing the (uninformative) full diff.
    if not snapshot_bytes:
        return False, (
            f"wireformat-immutability corruption: {slug} snapshot is empty at {path}\n"
            f"   action: run scripts/freeze_wireformat_snapshots.py --write to regenerate"
        )
    diff = _unified_diff(snapshot_bytes, live_bytes, str(path))
    msg = (
        f"wireformat-immutability drift: {slug} schema mismatch at {path}\n"
        f"   action: bump {model_cls.__name__}.schema_version + add migration; "
        f"then run scripts/freeze_wireformat_snapshots.py --write\n"
        f"--- diff (first {_DIFF_MAX_LINES} lines): ---\n{diff}"
    )
    return False, msg


def _write_one(slug: str, model_cls: type[BaseModel], path: Path) -> None:
    """Atomic write: render bytes to a sibling tempfile, then os.replace the snapshot.

    A SIGINT or filesystem error mid-write leaves the existing snapshot intact; never
    leaves the v1/ directory in a partially-rewritten state.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical_schema_bytes(model_cls)
    fd, tmp_str = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_str)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(payload)
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def _run_write(repo_root: Path, yes: bool, is_tty: bool) -> int:
    # Refuse non-tty without --yes: piping into the script with stdin closed would
    # otherwise skip the prompt and silently overwrite all 5 snapshots.
    if not is_tty and not yes:
        print(
            "wireformat-immutability refuse: non-interactive --write requires --yes\n"
            "   action: pass --yes when running in CI / pipelines / non-interactive shells",
            file=sys.stderr,
        )
        return _EXIT_FRAMEWORK
    if is_tty and not yes:
        try:
            answer = input(
                f"about to overwrite {len(_CONTRACTS)} snapshot files in "
                f"tests/contract_snapshots/v1/. Proceed? [y/N]: "
            )
        except EOFError:
            print("Aborted (EOF on stdin).", file=sys.stderr)
            return _EXIT_USER_ABORT
        if answer.strip().lower() != "y":
            # Distinct exit code so wrappers don't conflate user-cancel with drift.
            print("Aborted.", file=sys.stderr)
            return _EXIT_USER_ABORT
    for slug, model_cls in _CONTRACTS:
        path = _snapshot_path(repo_root, slug, 1)
        _write_one(slug, model_cls, path)
    print(
        f"wireformat-immutability write: {len(_CONTRACTS)} snapshots written to "
        f"tests/contract_snapshots/v1/"
    )
    return _EXIT_OK


def _run_check(repo_root: Path) -> int:
    # Accumulate BOTH missing-file errors and drift errors symmetrically; never
    # short-circuit after the first failure (so the user sees every problem at once
    # and doesn't have to re-run the script N times).
    any_missing = False
    any_drift = False
    expected_paths: set[Path] = set()
    for slug, model_cls in _CONTRACTS:
        path = _snapshot_path(repo_root, slug, 1)
        expected_paths.add(path)
        if not path.exists():
            print(
                f"wireformat-immutability bootstrap failure: snapshot file missing at {path}\n"
                f"   action: run scripts/freeze_wireformat_snapshots.py --write "
                f"to generate the v1 baseline",
                file=sys.stderr,
            )
            any_missing = True
            continue
        ok, msg = _verify_one(slug, model_cls, path)
        if not ok:
            print(msg, file=sys.stderr)
            any_drift = True

    # Snapshot-dir hygiene: catch unexpected JSON files in v1/ (a stale rename, an
    # accidental sibling). An orphan snapshot has no live contract pinning it, so
    # nothing else would surface the divergence.
    snapshot_dir = repo_root / "tests" / "contract_snapshots" / "v1"
    extras: list[Path] = []
    if snapshot_dir.is_dir():
        actual = {p for p in snapshot_dir.glob("*.json") if p.is_file()}
        extras = sorted(actual - expected_paths)
    if extras:
        print(
            "wireformat-immutability hygiene: unexpected snapshot file(s) in "
            f"{snapshot_dir}/:\n"
            + "\n".join(f"   {p.name}" for p in extras)
            + "\n   action: either add the contract to _WIRE_FORMAT_REGISTRY "
            "(see ADR-024) or remove the orphan file.",
            file=sys.stderr,
        )
        any_drift = True

    if any_missing:
        return _EXIT_FRAMEWORK
    if any_drift:
        return _EXIT_DRIFT
    print(
        f"wireformat-immutability check: {len(_CONTRACTS)} contracts match snapshots at "
        f"tests/contract_snapshots/v1/"
    )
    return _EXIT_OK


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

    # --yes is only meaningful with --write; flag it loudly rather than silently ignoring.
    if args.yes and not args.write:
        parser.error("--yes is only valid with --write")

    if args.write:
        return _run_write(_REPO_ROOT, args.yes, sys.stdin.isatty())
    return _run_check(_REPO_ROOT)


if __name__ == "__main__":
    sys.exit(main())
