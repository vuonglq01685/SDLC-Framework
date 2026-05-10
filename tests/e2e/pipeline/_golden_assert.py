"""Pipeline golden assertion helpers — extracted from conftest.py (LOC cap, NFR-MAINT-3).

``PipelineObservation`` is referenced only as a type annotation; the import is
deferred to TYPE_CHECKING so this module can be imported by conftest.py without
a circular import at runtime.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from e2e.pipeline.conftest import PipelineObservation


# ---------------------------------------------------------------------------
# Canonical JSON helper (Architecture §496-§515, Story 1.21 AC1.3)
# ---------------------------------------------------------------------------


def _canon_json(obj: object) -> bytes:
    """Canonicalize to JSON bytes for human-reviewable Tier-2 goldens.

    PR-DR6 sanctioned deviation: uses ``indent=2`` for PR-diff legibility
    (ADR-027 amendment) + sort_keys for byte-stability + compact separators
    for determinism.
    """
    return (
        json.dumps(
            obj,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            indent=2,
        ).encode("utf-8")
        + b"\n"
    )


# ---------------------------------------------------------------------------
# Journal hash helper (PR3 — Tier-2 ts-stripped to align with Tier-1)
# ---------------------------------------------------------------------------

_NO_JOURNAL_SENTINEL: str = "<no-journal>\n"
_EMPTY_JOURNAL_SENTINEL: str = "<empty-journal>\n"


def _hash_pipeline_journal(journal_path: Path) -> str:
    """Compute Tier-2 journal hash with ts-stripping (PR3).

    Aligns with Tier-1's ``_hash_journal_no_ts``: when Story 2A.3 lands a real
    journal-writing dispatcher, both tiers see byte-stable hashes.

    Distinct sentinels:
      - file does not exist OR has zero bytes → ``<no-journal>``
      - file exists but contains no non-blank JSON entries → ``<empty-journal>``
    """
    if not journal_path.exists() or journal_path.stat().st_size == 0:
        return _NO_JOURNAL_SENTINEL
    raw_lines = journal_path.read_bytes().splitlines()
    canon_lines: list[bytes] = []
    for lineno, line in enumerate(raw_lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            decoded = stripped.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AssertionError(
                f"Pipeline journal corruption at {journal_path}:{lineno} — "
                f"line is not valid UTF-8: {exc}."
            ) from exc
        try:
            entry: object = json.loads(decoded)
        except json.JSONDecodeError as exc:
            raise AssertionError(
                f"Pipeline journal corruption at {journal_path}:{lineno} — "
                f"line is not valid JSON: {exc}."
            ) from exc
        if not isinstance(entry, dict):
            raise AssertionError(
                f"Pipeline journal shape drift at {journal_path}:{lineno} — "
                f"expected a JSON object, got {type(entry).__name__}."
            )
        entry.pop("ts", None)
        canon = json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        canon_lines.append(canon)
    if not canon_lines:
        return _EMPTY_JOURNAL_SENTINEL
    combined = b"\n".join(canon_lines)
    return hashlib.sha256(combined).hexdigest() + "\n"


# ---------------------------------------------------------------------------
# Central assertion helper
# ---------------------------------------------------------------------------


def _compare_one_pipeline_golden(
    filename: str,
    actual: bytes,
    goldens_dir: Path,
    action_hint: str,
) -> str | None:
    """Tier-2 mirror of cli/conftest._compare_one_golden (PR28 — symmetric handling)."""
    golden_path = goldens_dir / filename
    if not golden_path.exists():
        return f"Golden file missing: {golden_path}\n{action_hint}"
    expected = golden_path.read_bytes()
    if actual == expected:
        return None
    return (
        f"GOLDEN MISMATCH: {golden_path}\n"
        f"  expected: {expected!r}\n"
        f"  actual:   {actual!r}\n"
        f"{action_hint}"
    )


def assert_pipeline_goldens(
    scenario_dir: Path,
    observed: PipelineObservation,
    update: bool,
) -> None:
    """Assert (or update) the four Tier-2 golden files (AC3.3).

    Golden files under <scenario_dir>/goldens/:
      final_journal_sha256       — ts-stripped sha256 of journal.log or sentinel (PR3)
      signoff_hashes.json        — canonical JSON array of phase signoff records
      hook_chain_order.json      — canonical JSON array of hook-fire records
      specialist_invocations.json — canonical JSON array of dispatch records
    """
    goldens_dir = scenario_dir / "goldens"
    goldens_dir.mkdir(parents=True, exist_ok=True)

    journal_hash = _hash_pipeline_journal(observed.final_journal_path)

    _action_hint = (
        "action: review the diff. If intentional, regenerate via "
        "'pytest tests/e2e/pipeline/ --update-goldens' and cite the change in the PR Change Log."
    )

    actuals: dict[str, bytes] = {
        "final_journal_sha256": journal_hash.encode("utf-8"),
        "signoff_hashes.json": _canon_json([dict(r) for r in observed.signoff_hashes]),
        "hook_chain_order.json": _canon_json([dict(r) for r in observed.hook_chain]),
        "specialist_invocations.json": _canon_json(
            [dict(r) for r in observed.specialist_invocations]
        ),
    }

    if update:
        for filename, content in actuals.items():
            (goldens_dir / filename).write_bytes(content)
        return

    # PR28: symmetric error collection with cli/conftest.
    errors = [
        err
        for filename, actual in actuals.items()
        if (err := _compare_one_pipeline_golden(filename, actual, goldens_dir, _action_hint))
    ]

    if errors:
        raise AssertionError("\n\n".join(errors))
