"""Path-resolution guards for `sdlc verify` (Story 2A.10 + 3.4 adopted symlinks)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import typer

from sdlc.cli.output import emit_error


def _reject_symlink_ancestors(
    *,
    ctx: typer.Context,
    root: Path,
    parts: tuple[str, ...],
    artifact_id: str,
    adopted_targets: frozenset[str],
) -> None:
    """PC2: walk every parent component from `root` toward the artifact and
    reject if any is a symlink. ``Path.resolve()`` silently follows symlinks
    so a `01-Requirement/` that is itself a symlink to an out-of-tree path
    yields ``resolved`` AND ``target_root`` both pointing at the symlink
    target, defeating the ``relative_to`` containment check. Walking with
    ``is_symlink()`` closes this gap. Covers Windows reparse points via
    ``Path.is_symlink`` ST_REPARSE_POINT semantics.
    """
    walk = root
    for i, part in enumerate(parts):
        walk = walk / part
        try:
            if walk.is_symlink():
                is_leaf = i == len(parts) - 1
                if is_leaf and artifact_id in adopted_targets:
                    continue
                emit_error(
                    "ERR_PATH_TRAVERSAL",
                    f"artifact_id path contains a symlink component '{part}'; "
                    "refusing to resolve (symlink components disallowed under "
                    "01-Requirement/)",
                    ctx=ctx,
                    details={"artifact_id": artifact_id, "symlink_at": str(walk)},
                )
        except OSError:
            # Broken symlink or permission error on a component — let the
            # explicit resolve() in the caller surface the precise error.
            break


def _assert_resolved_containment(
    *,
    ctx: typer.Context,
    resolved: Path,
    target_root: Path,
    root_resolved: Path,
    artifact_id: str,
    adopted_sources: Mapping[str, str],
) -> None:
    """Ensure the resolved path stays under 01-Requirement/.

    For a known-adopted leaf symlink the slot legitimately resolves OUTSIDE
    01-Requirement/, so containment is relaxed — but only to the EXACT source the
    manifest recorded (defense-in-depth, DN2): membership authorizes the slot name,
    the source binding authorizes the destination, so a repointed on-disk symlink or
    a forged manifest target cannot redirect verify to a different in-repo file.
    """
    try:
        resolved.relative_to(target_root)
    except ValueError:
        source = adopted_sources.get(artifact_id)
        if source is not None:
            try:
                resolved.relative_to(root_resolved)
            except ValueError:
                emit_error(
                    "ERR_PATH_TRAVERSAL",
                    "adopted artifact symlink escapes project root",
                    ctx=ctx,
                    details={"artifact_id": artifact_id, "resolved": str(resolved)},
                )
            expected = (root_resolved / source).resolve()
            if resolved != expected:
                emit_error(
                    "ERR_PATH_TRAVERSAL",
                    "adopted artifact symlink does not resolve to its recorded source",
                    ctx=ctx,
                    details={
                        "artifact_id": artifact_id,
                        "resolved": str(resolved),
                        "expected": str(expected),
                    },
                )
        else:
            emit_error(
                "ERR_PATH_TRAVERSAL",
                "artifact_id resolves outside 01-Requirement/ "
                "(symlink escape or directory traversal)",
                ctx=ctx,
                details={"artifact_id": artifact_id, "resolved": str(resolved)},
            )
