"""Unit tests for engine/auto_mad.py (Story 4.11)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from sdlc.engine.stop_triggers import StopDecision
from sdlc.journal import iter_entries
from sdlc.signoff import read_record

pytestmark = pytest.mark.unit

_TS = "2026-06-22T12:00:00.000Z"
_OPTIONS = textwrap.dedent(
    """\
    # Clarification Options

    ## Option 1: Webhooks
    ### Pros
    - Real-time
    ### Cons
    - Public endpoint
    ### Risks
    - Retries

    ## Option 2: Polling
    ### Pros
    - Simple
    ### Cons
    - Latency
    ### Risks
    - Rate limits
    """
)


def test_extract_first_option_returns_option_one_body() -> None:
    from sdlc.engine.auto_mad import extract_first_option

    body = extract_first_option(_OPTIONS)
    assert body is not None
    assert "Webhooks" in body
    assert "Polling" not in body


def test_extract_first_option_absent_options_returns_none() -> None:
    from sdlc.engine.auto_mad import extract_first_option

    assert extract_first_option("# no options here\n") is None


@pytest.mark.asyncio
async def test_resolve_clarification_writes_resolution_and_removes_open_file(
    tmp_path: Path,
) -> None:
    from sdlc.engine.auto_mad import resolve_clarification

    clar_dir = tmp_path / ".claude" / "state" / "clarifications" / "clar-abc123"
    clar_dir.mkdir(parents=True)
    open_path = clar_dir / "open_clarification.md"
    open_path.write_text("# Open\n\nNeed a decision.\n", encoding="utf-8")
    (clar_dir / "options.md").write_text(_OPTIONS, encoding="utf-8")
    journal = tmp_path / ".claude" / "state" / "journal.log"
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.touch()

    stop = StopDecision(
        fired=True,
        trigger="open_clarification",
        target=str(open_path),
        reason="test",
    )
    await resolve_clarification(
        tmp_path,
        stop=stop,
        journal_path=journal,
        correlation_id="cid-1",
        now_utc=_TS,
    )

    assert not open_path.exists()
    resolution = clar_dir / "resolution.md"
    assert resolution.is_file()
    text = resolution.read_text(encoding="utf-8")
    assert "ai-mad-mode" in text
    assert "clar-abc123" in text
    assert "Webhooks" in text
    mad_entries = [e for e in iter_entries(journal) if e.kind == "auto_mad_resolve"]
    assert len(mad_entries) == 1
    assert mad_entries[0].payload["target"] == ".claude/state/clarifications/clar-abc123"
    assert "Webhooks" in str(mad_entries[0].payload["decision"])


@pytest.mark.asyncio
async def test_resolve_clarification_without_options_uses_synth_pick_sentinel(
    tmp_path: Path,
) -> None:
    from sdlc.engine.auto_mad import _SYNTH_PICK_SENTINEL, resolve_clarification

    clar_dir = tmp_path / ".claude" / "state" / "clarifications" / "clar-nopts"
    clar_dir.mkdir(parents=True)
    open_path = clar_dir / "open_clarification.md"
    open_path.write_text("# Open\n", encoding="utf-8")
    journal = tmp_path / ".claude" / "state" / "journal.log"
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.touch()

    await resolve_clarification(
        tmp_path,
        stop=StopDecision(
            fired=True,
            trigger="open_clarification",
            target=str(open_path),
        ),
        journal_path=journal,
        correlation_id="cid-2",
        now_utc=_TS,
    )
    mad_entries = [e for e in iter_entries(journal) if e.kind == "auto_mad_resolve"]
    assert mad_entries[0].payload["decision"] == _SYNTH_PICK_SENTINEL


def _write_phase2_unsigned_with_draft(tmp_path: Path) -> None:
    from sdlc.signoff import ArtifactRef, SignoffRecord, write_record
    from sdlc.signoff.generator import generate_signoff_md
    from sdlc.signoff.hasher import compute_artifact_hash

    p1 = tmp_path / "01-Requirement" / "01-PRODUCT.md"
    p1.parent.mkdir(parents=True, exist_ok=True)
    p1.write_text("# Product\n", encoding="utf-8")
    p2 = tmp_path / "02-Architecture" / "ARCHITECTURE.md"
    p2.parent.mkdir(parents=True, exist_ok=True)
    p2.write_text("# Arch\n", encoding="utf-8")

    h1 = compute_artifact_hash(p1, repo_root=tmp_path)
    write_record(
        SignoffRecord(
            phase=1,
            artifacts=(ArtifactRef(path="01-Requirement/01-PRODUCT.md", hash=h1),),
            approved_by="human",
            approved_at=_TS,
            drafted_at="2026-06-10T09:00:00.000Z",
            validated_at=_TS,
        ),
        repo_root=tmp_path,
    )
    generate_signoff_md(2, repo_root=tmp_path)


@pytest.mark.asyncio
async def test_mad_sign_writes_record_with_ai_mad_mode(tmp_path: Path) -> None:
    from sdlc.engine.auto_mad import mad_sign_phase

    _write_phase2_unsigned_with_draft(tmp_path)
    journal = tmp_path / ".claude" / "state" / "journal.log"
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.touch()

    stop = StopDecision(
        fired=True,
        trigger="signoff_required",
        target="02-Architecture/SIGNOFF.md",
        reason="test",
    )
    await mad_sign_phase(
        tmp_path,
        stop=stop,
        journal_path=journal,
        correlation_id="cid-3",
        now_utc=_TS,
    )

    record = read_record(phase=2, repo_root=tmp_path)
    assert record.approved_by == "ai-mad-mode"
    kinds = [e.kind for e in iter_entries(journal)]
    assert "signoff_recorded" in kinds
    assert "auto_mad_resolve" in kinds
    mad = next(e for e in iter_entries(journal) if e.kind == "auto_mad_resolve")
    assert mad.after_hash == "sha256:" + "0" * 64
    assert mad.payload["target"] == "02-Architecture/SIGNOFF.md"


@pytest.mark.asyncio
async def test_maybe_mad_resolve_stop_returns_false_for_other_triggers() -> None:
    from sdlc.engine.auto_mad import maybe_mad_resolve_stop

    resolved = await maybe_mad_resolve_stop(
        Path("/tmp"),
        stop=StopDecision(
            fired=True,
            trigger="agent_failed",
            target="x",
            reason="test",
        ),
        journal_path=Path("/tmp/journal.log"),
        correlation_id="cid-4",
    )
    assert resolved is False
