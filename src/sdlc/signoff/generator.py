"""Signoff draft generator (FR11, AC1/D1, AC3, AC9, Story 2A.12).

Decision AC1/D1: generate SIGNOFF.md mechanically (no AI dispatch). Deterministic
hash computation; specialist dispatch deferred to Story 2B.8.

Decision AC3/D2 (re-decided 2026-05-14 per code-review DR3): SIGNOFF.md write
bypasses the hook chain — phase_gate.py:137 unconditionally allows leading "01-"
paths, which incidentally covers the SIGNOFF.md write. True D1 (intent-aware
``write_intent="signoff_draft"`` threading + phase_gate ``target_kind == "signoff"``
branch) is tracked as ``EPIC-2A-DEBT-SIGNOFF-WRITE-INTENT``.

LOC target: ≤ 200.
"""

from __future__ import annotations

import datetime
from pathlib import Path, PurePosixPath

import yaml

from sdlc.errors import SignoffError
from sdlc.signoff.hasher import compute_artifact_hash
from sdlc.signoff.records import _PHASE_DIR_MAP, _write_bytes_to_disk

_SIGNOFF_FILENAME = "SIGNOFF.md"
_FORBIDDEN_PATH_CHARS = ("```",)  # P11: triple-backtick would corrupt fenced block


def _now_rfc3339_utc_ms() -> str:
    """RFC 3339 UTC with millisecond precision.

    Module-local because ``signoff/`` cannot import ``cli/`` or ``ids/``
    per the boundary-validator config (Architecture §1052). P16's
    canonical-helper-reuse intent is deferred until a shared time helper
    lives in an already-permitted dependency (``contracts`` or ``state``).
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    millis = now.microsecond // 1000
    return f"{now.strftime('%Y-%m-%dT%H:%M:%S')}.{millis:03d}Z"


def _collect_artifacts(
    phase_dir: Path, signoff_path: Path, repo_root: Path
) -> list[dict[str, str]]:
    """Enumerate + hash all files under phase_dir, excluding signoff_path.

    Returns list of {"path": <repo-relative POSIX>, "hash": <sha256:hex>} dicts
    sorted lexicographically by path (AC3 byte-stable ordering).

    P12: symlinks are skipped — a symlink under the phase dir pointing outside
    the tree would otherwise be hashed and listed (path traversal in audit log).
    """
    artifacts: list[dict[str, str]] = []
    for p in sorted(
        phase_dir.rglob("*"), key=lambda x: str(PurePosixPath(x.relative_to(repo_root)))
    ):
        if p.is_symlink():
            continue
        if not p.is_file():
            continue
        if p == signoff_path:
            continue
        rel = str(PurePosixPath(p.relative_to(repo_root)))
        # P11: refuse any path containing triple-backticks (would close the
        # fenced ```signoff block prematurely and corrupt round-trip).
        for forbidden in _FORBIDDEN_PATH_CHARS:
            if forbidden in rel:
                raise SignoffError(
                    f"artifact path contains forbidden character sequence {forbidden!r}: {rel}; "
                    "rename the file before generating signoff",
                    details={
                        "step": "generate_signoff_md",
                        "path": rel,
                        "forbidden": forbidden,
                    },
                )
        h = compute_artifact_hash(p, repo_root=repo_root)
        artifacts.append({"path": rel, "hash": h})
    return artifacts


def _render_signoff_md(
    phase: int,
    artifacts: list[dict[str, str]],
    drafted_at: str,
) -> str:
    """Render the full SIGNOFF.md content (Markdown preamble + fenced YAML block).

    P11 (YAML safety): the artifact list inside the fenced block is emitted via
    ``yaml.safe_dump`` so paths containing YAML-significant characters (``:``,
    ``#``, leading ``-``, ``[`` etc.) round-trip correctly. Top-level scalars
    (``schema_version``, ``phase``, ``approved``, ``approved_by``,
    ``approved_at``, ``drafted_at``) are well-typed and use direct literal
    emission.

    DR4: ``schema_version: 1`` is emitted as the first key inside the fenced
    block for forward-compatibility — see ``_SignoffMdDraft`` in records.py.
    """
    # P17: Markdown table divider fixed — was "|------|---------- |" (stray space)
    rows = "\n".join(f"| {a['path']} | {a['hash']} |" for a in artifacts)
    table = f"| Path | SHA-256 |\n|------|---------|\n{rows}"

    # P11: YAML-safe emission for the artifact list (handles special chars
    # in paths). yaml.safe_dump produces block-style with sort_keys=False so
    # the artifact-write order is preserved (already sorted by _collect_artifacts).
    artifacts_yaml = yaml.safe_dump(
        artifacts,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
        indent=2,
    ).rstrip("\n")
    # yaml.safe_dump for a top-level list yields lines starting with "- ";
    # indent them by 2 spaces so they nest under "artifacts:".
    artifacts_yaml_indented = "\n".join(f"  {line}" for line in artifacts_yaml.splitlines())

    yaml_block = (
        f"schema_version: 1\n"
        f"phase: {phase}\n"
        f"artifacts:\n{artifacts_yaml_indented}\n"
        f"approved: false\n"
        f"approved_by: null\n"
        f"approved_at: null\n"
        f"drafted_at: {drafted_at}\n"
    )

    return (
        f"# Phase {phase} Signoff\n\n"
        f"## Artifacts\n\n"
        f"{table}\n\n"
        f"## Instructions\n\n"
        "Edit the signoff block below: set `approved: true` "
        "and fill in `approved_by` with your name.\n"
        f"Then run `sdlc scan` to validate hashes and record the canonical approval.\n\n"
        f"```signoff\n{yaml_block}```\n"
    )


def generate_signoff_md(phase: int, *, repo_root: Path) -> tuple[Path, int]:
    """Generate SIGNOFF.md draft for the given phase under its phase directory.

    AC3: enumerates all files under the phase directory (lexicographic order),
    excludes SIGNOFF.md itself, computes sha256 per artifact, writes the draft.

    P10: returns a tuple of (path, artifact_count) so callers can record the
    count in the journal without re-parsing the file. Previous return type was
    bare ``Path``.

    P8: SIGNOFF.md is written via the atomic ``_write_bytes_to_disk`` helper
    (fsync + os.replace) so a torn write under SIGTERM/power-loss can never
    leave a partial file visible to ``read_signoff_md_draft``.

    Raises SignoffError with ERR_NO_ARTIFACTS code (via ``exc.details["code"]``)
    if the phase directory is empty or does not exist.
    """
    phase_dir_name = _PHASE_DIR_MAP.get(phase)
    if phase_dir_name is None:
        raise SignoffError(
            f"phase out of range for signoff generation: must be 1 or 2; got {phase}",
            details={"step": "generate_signoff_md", "phase": phase},
        )

    phase_dir = repo_root / phase_dir_name
    signoff_path = phase_dir / _SIGNOFF_FILENAME

    if not phase_dir.exists():
        # P3: message body has NO error-code prefix — the CLI layer adds it
        # via emit_error("ERR_NO_ARTIFACTS", ...). Previous emission produced
        # "ERR_NO_ARTIFACTS: ERR_NO_ARTIFACTS: …" doubled.
        raise SignoffError(
            f"no artifacts found under {phase_dir_name}; "
            "run the phase commands first (e.g. /sdlc-start, /sdlc-epics, /sdlc-stories) "
            "before generating signoff",
            details={
                "step": "generate_signoff_md",
                "code": "ERR_NO_ARTIFACTS",
                "phase": phase,
                "dir": str(phase_dir),
            },
        )

    artifacts = _collect_artifacts(phase_dir, signoff_path, repo_root)

    if not artifacts:
        raise SignoffError(
            f"no artifacts found under {phase_dir_name}; "
            "run the phase commands first (e.g. /sdlc-start, /sdlc-epics, /sdlc-stories) "
            "before generating signoff",
            details={
                "step": "generate_signoff_md",
                "code": "ERR_NO_ARTIFACTS",
                "phase": phase,
                "dir": str(phase_dir),
            },
        )

    drafted_at = _now_rfc3339_utc_ms()
    content = _render_signoff_md(phase, artifacts, drafted_at)

    # P8: atomic write (fsync + os.replace) — same primitive write_record uses.
    _write_bytes_to_disk(signoff_path, content.encode("utf-8"))
    return signoff_path, len(artifacts)
