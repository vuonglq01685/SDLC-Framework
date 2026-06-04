"""Pass 2 — offer to symlink detected artifacts into the canonical layout (Story 3.3 + 3.6).

`offer_symlinks` walks the frozen `detected[]` Pass 1 produced and, for each offerable artifact
(non-empty `suggested_target`) at or above the integer `auto_accept_threshold`, accepts it via
`_accept.accept_one_artifact` (create / conflict-resolve), records every accepted mapping in
`.claude/state/adopted-symlinks.json` (the 7th frozen wire-format contract), and journals a
`symlink_accepted` event per symlink. The per-artifact accept + conflict-resolution mechanics
live in `_accept.py` (NFR-MAINT-3 ≤400 LOC split); this module owns the offer LOOP + manifest I/O.

The pure core DECIDES (threshold gating, conflict handling, recording); the `cli` layer PROMPTS.
Interactivity, the threshold, and a warning sink are dependency-injected from `cli/adopt.py`
(mirroring Story 3.2's `git_signal` DI) so `adopt/` keeps its boundary: NO `cli`/`engine`/
`dispatcher`/`runtime` import, and no `print` (human output goes through `cli/output`).

  * confirm is not None  ⇒ interactive: ≥ threshold → prompt `[Y/n/edit]`; below → silent skip.
  * confirm is None      ⇒ non-interactive: ≥ threshold → auto-accept; below → skip + warn.

Source files are never modified (NFR-REL-6): the only writes are the symlinks at canonical
target paths (outside `.claude/`, the one sanctioned exception) and the manifest + journal
(under `.claude/`, pre-guarded by `assert_path_under_claude`). The manifest is flushed ONCE
after the loop; the journal is the audit source of truth (Story 3.5 rollback / 3.6 idempotency
rebuild from it), and the manifest is a derived cache. Each artifact is handled fail-soft.
"""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from sdlc.adopt.invariant import assert_path_under_claude
from sdlc.adopt.passes._accept import (
    ConflictCallback,
    ConflictContext,
    ConflictDecision,
    ConflictKind,
    WarnCallback,
    accept_one_artifact,
    append_adopt_rerun_event,
)
from sdlc.adopt.passes._symlink import resolve_target
from sdlc.concurrency.io_primitives import atomic_write_bytes
from sdlc.config.project import DEFAULT_AUTO_ACCEPT_THRESHOLD
from sdlc.contracts.adopt_report import DetectedArtifact
from sdlc.contracts.adopted_symlinks import AdoptedSymlinks, SymlinkMapping
from sdlc.ids.clock import now_rfc3339_utc_ms

__all__ = [
    "ConfirmCallback",
    "ConflictCallback",
    "ConflictContext",
    "ConflictDecision",
    "ConflictKind",
    "SymlinkDecision",
    "WarnCallback",
    "offer_symlinks",
]

_MANIFEST_REL: Final[str] = ".claude/state/adopted-symlinks.json"


@dataclass(frozen=True)
class SymlinkDecision:
    """Outcome of an interactive `[Y/n/edit]` offer for one candidate (the `cli` layer builds it).

    `target` is the (possibly edited, D3) repo-relative POSIX slot to symlink into; it is only
    honoured when `accept` is True.
    """

    accept: bool
    target: str


# The injected interactive prompt: given the artifact + its suggested target, decide.
ConfirmCallback = Callable[[DetectedArtifact, str], SymlinkDecision]


def _manifest_bytes(manifest: AdoptedSymlinks) -> bytes:
    """Canonical bytes for `adopted-symlinks.json` — identical scheme to `driver._report_bytes`."""
    text = json.dumps(
        manifest.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return (unicodedata.normalize("NFC", text) + "\n").encode("utf-8")


def _load_existing_mappings(
    root: Path, *, warn: WarnCallback | None = None
) -> list[SymlinkMapping]:
    """Return any prior manifest's mappings (preserved across resume/idempotency), or [].

    A corrupt/unreadable prior manifest must not crash Pass 2 — but it is NOT swallowed
    silently: a warning is surfaced (the journal remains the audit source of truth that 3.5
    rollback and 3.6 idempotency rebuild from, so the manifest is a derived cache we can rebuild).
    """
    manifest_path = root / _MANIFEST_REL
    if not manifest_path.exists():
        return []
    try:
        return list(
            AdoptedSymlinks.model_validate_json(manifest_path.read_text(encoding="utf-8")).mappings
        )
    except (OSError, ValueError) as exc:
        if warn is not None:
            warn(
                f"existing {_MANIFEST_REL} is unreadable ({exc}); starting from an empty manifest "
                "(prior mappings remain recoverable from the journal)"
            )
        return []


def _write_manifest(root: Path, mappings: Sequence[SymlinkMapping]) -> None:
    """Atomically (re)write the manifest, pre-guarded to stay under `.claude/` (AC6)."""
    manifest_path = (root / _MANIFEST_REL).resolve()
    assert_path_under_claude(root, manifest_path)
    atomic_write_bytes(manifest_path, _manifest_bytes(AdoptedSymlinks(mappings=tuple(mappings))))


def _select_target(
    artifact: DetectedArtifact,
    *,
    confirm: ConfirmCallback | None,
) -> str | None:
    if confirm is None:
        return resolve_target(artifact.suggested_target, artifact.path)
    decision = confirm(artifact, artifact.suggested_target)
    if not decision.accept:
        return None
    return resolve_target(decision.target, artifact.path)


def offer_symlinks(  # noqa: C901
    root: Path,
    detected: Sequence[DetectedArtifact],
    *,
    confirm: ConfirmCallback | None = None,
    auto_accept_threshold: int = DEFAULT_AUTO_ACCEPT_THRESHOLD,
    warn: WarnCallback | None = None,
    journal_path: Path | None = None,
    conflict: ConflictCallback | None = None,
) -> None:
    """Offer + create symlinks for `detected` artifacts (Story 3.3 implements; 3.1 was a no-op).

    Args:
        root: repository root.
        detected: frozen Pass 1 output (read-only); only non-empty-`suggested_target` artifacts
            are offerable (detect-only kinds carry an empty target per Story 3.2 D1).
        confirm: interactive `[Y/n/edit]` callback (injected by `cli`); None ⇒ non-interactive.
        auto_accept_threshold: integer-percent confidence gate (D1). ≥ ⇒ offer/accept; below ⇒
            silent skip (interactive) or skip+warn (non-interactive).
        warn: human-warning sink (injected by `cli`, routes through `cli/output`); None ⇒ drop.
        journal_path: where to append `symlink_accepted` events; None ⇒ no journaling (resume /
            non-adopt no-op default, so 3.1's orchestrator-ordering test stays unaffected).
        conflict: interactive conflict-resolution callback (injected by `cli`, Story 3.6);
            None ⇒ a target conflict skips-and-warns (no destructive op without consent).
    """
    had_prior_manifest = (root / _MANIFEST_REL).exists()
    mappings: list[SymlinkMapping] = _load_existing_mappings(root, warn=warn)
    recorded_targets: set[str] = {m.target for m in mappings}
    initial_mapping_count = len(mappings)
    skipped_existing = 0
    changed = False

    for artifact in detected:
        if not artifact.suggested_target:
            continue
        if artifact.confidence < auto_accept_threshold:
            if confirm is None and warn is not None:
                warn(
                    f"skipping {artifact.path} ({artifact.kind}, confidence "
                    f"{artifact.confidence}) — below auto-accept threshold {auto_accept_threshold}"
                )
            continue

        resolved_default = resolve_target(artifact.suggested_target, artifact.path)
        if resolved_default in recorded_targets:
            skipped_existing += 1
            # AC4(iii): tell the user this candidate was already decided in a prior run, rather
            # than skipping it silently (the resume "already decided" notice).
            if warn is not None:
                warn(f"skipping {artifact.path}: already adopted (target {resolved_default})")
            continue

        final_target = _select_target(artifact, confirm=confirm)
        if final_target is None:
            continue
        if final_target in recorded_targets:
            skipped_existing += 1
            if warn is not None:
                warn(f"skipping {artifact.path}: already adopted (target {final_target})")
            continue

        if accept_one_artifact(
            root,
            artifact,
            final_target,
            mappings,
            recorded_targets,
            journal_path=journal_path,
            conflict=conflict,
            warn=warn,
        ):
            changed = True

    new_adoptions = len(mappings) - initial_mapping_count
    # D3(a): emit ONE `adopt_re_run` summary whenever this is a re-run (a prior manifest
    # existed) — NOT gated on activity, so a genuine re-run with nothing to do still records it.
    if had_prior_manifest and journal_path is not None:
        append_adopt_rerun_event(
            journal_path,
            new_adoptions=new_adoptions,
            skipped_existing=skipped_existing,
            ts=now_rfc3339_utc_ms(),
        )

    if changed:
        _write_manifest(root, mappings)
