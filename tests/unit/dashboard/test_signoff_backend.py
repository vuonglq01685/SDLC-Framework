"""``GET /api/signoff`` — real signoff read seam (Story 5.14 Task 1).

Covers the server-side wire-up: `sdlc.signoff.states.compute_state` /
`sdlc.signoff.records.read_record` drive the response (never re-parsing YAML
directly), the wire values are byte-identical to `SignoffState` enum values
(no translation table), the `invalidated-by-replan` phase surfaces the
persisted replan scope read through the `journal` seam (D2, no `engine`
recompute), and a malformed canonical record fails loud (propagates) rather
than silently demoting to `awaiting-signoff`.
"""

from __future__ import annotations

import json
import textwrap
import time
from pathlib import Path

import pytest

from sdlc.contracts.journal_entry import JournalEntry
from sdlc.dashboard.server import find_free_port, serve_dashboard_in_thread
from sdlc.journal.writer import allocate_next_seq_for_append_sync, append_sync
from sdlc.signoff.records import ArtifactRef, SignoffRecord, write_record
from sdlc.signoff.states import SignoffState

from ._http import http_get

pytestmark = pytest.mark.unit

_VALID_HASH = "sha256:" + "a" * 64
_TS1 = "2026-05-10T11:00:00.000Z"
_TS2 = "2026-05-10T12:00:00.000Z"
_TS_INVAL = "2026-05-10T13:00:00.000Z"
_PHASE_DIR = {1: "01-Requirement", 2: "02-Architecture"}
_JOURNAL_REL = ".claude/state/journal.log"


def _write_draft(repo_root: Path, phase: int) -> None:
    phase_dir = repo_root / _PHASE_DIR[phase]
    phase_dir.mkdir(parents=True, exist_ok=True)
    (phase_dir / "SIGNOFF.md").write_text(
        textwrap.dedent(f"""\
            ---
            schema_version: 1
            phase: {phase}
            artifacts:
              - path: "{_PHASE_DIR[phase]}/PRODUCT.md"
                hash: "{_VALID_HASH}"
            approved: false
            approved_by: null
            approved_at: null
            drafted_at: "{_TS1}"
            ---
        """),
        encoding="utf-8",
    )


def _write_approved(repo_root: Path, phase: int) -> SignoffRecord:
    record = SignoffRecord(
        phase=phase,
        artifacts=(ArtifactRef(path=f"{_PHASE_DIR[phase]}/PRODUCT.md", hash=_VALID_HASH),),
        approved_by="alice",
        approved_at=_TS2,
        drafted_at=_TS1,
        validated_at=_TS2,
    )
    write_record(record, repo_root=repo_root)
    return record


def _write_invalidated(repo_root: Path, phase: int, *, invalidated_at: str) -> SignoffRecord:
    from sdlc.signoff.records import _canonicalize_record, _signoff_path, _write_bytes_to_disk

    record = SignoffRecord(
        phase=phase,
        artifacts=(ArtifactRef(path=f"{_PHASE_DIR[phase]}/PRODUCT.md", hash=_VALID_HASH),),
        approved_by="alice",
        approved_at=_TS2,
        drafted_at=_TS1,
        validated_at=_TS2,
        invalidated_at=invalidated_at,
        invalidated_reason="replan",
    )
    target = _signoff_path(phase, repo_root)
    _write_bytes_to_disk(target, _canonicalize_record(record))
    return record


def _append_replan_invalidated(
    repo_root: Path,
    *,
    ts: str,
    scope: str = "01-Requirement/PRODUCT.md",
    scope_phase: int = 1,
    downstream_artifacts: list[str] | None = None,
    reason: str = "requirements changed",
) -> None:
    journal_path = repo_root / _JOURNAL_REL
    seq = allocate_next_seq_for_append_sync(journal_path)
    entry = JournalEntry(
        monotonic_seq=seq,
        ts=ts,
        kind="replan_invalidated",
        actor="cli:replan",
        target_id=scope,
        before_hash=None,
        after_hash=_VALID_HASH,
        payload={
            "scope": scope,
            "scope_phase": scope_phase,
            "downstream_artifacts": downstream_artifacts or ["02-Architecture/ARCHITECTURE.md"],
            "downstream_count": len(downstream_artifacts or ["02-Architecture/ARCHITECTURE.md"]),
            "reason": reason,
        },
    )
    append_sync(entry, journal_path=journal_path)


def _start_dashboard(repo_root: Path) -> tuple[str, int, object, object]:
    port = find_free_port()
    server, thread = serve_dashboard_in_thread(repo_root=repo_root, port=port)
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 5.0
    last_status: int | None = None
    while time.monotonic() < deadline:
        try:
            status, _, _ = http_get(base_url, "/api/signoff", port=port)
            last_status = status
            if status == 200:
                break
        except OSError:
            time.sleep(0.05)
    else:
        pytest.fail(f"dashboard server did not become ready (last status={last_status})")
    return base_url, port, server, thread


def _stop_dashboard(server: object, thread: object) -> None:
    server.shutdown()  # type: ignore[attr-defined]
    server.server_close()  # type: ignore[attr-defined]
    thread.join(timeout=5)  # type: ignore[attr-defined]


class TestRealStateWiring:
    def test_all_phases_awaiting_when_nothing_present(self, tmp_path: Path) -> None:
        base_url, port, server, thread = _start_dashboard(tmp_path)
        try:
            status, _, body = http_get(base_url, "/api/signoff", port=port)
            assert status == 200
            payload = json.loads(body.decode("utf-8"))
            for phase in ("1", "2", "3"):
                assert payload["phases"][phase]["state"] == SignoffState.AWAITING_SIGNOFF.value
                assert payload["phases"][phase]["invalidated_at"] is None
                assert payload["phases"][phase]["invalidated_reason"] is None
        finally:
            _stop_dashboard(server, thread)

    def test_phase_drafted_not_approved(self, tmp_path: Path) -> None:
        _write_draft(tmp_path, phase=2)
        base_url, port, server, thread = _start_dashboard(tmp_path)
        try:
            _, _, body = http_get(base_url, "/api/signoff", port=port)
            payload = json.loads(body.decode("utf-8"))
            assert payload["phases"]["2"]["state"] == SignoffState.DRAFTED_NOT_APPROVED.value
        finally:
            _stop_dashboard(server, thread)

    def test_phase_approved(self, tmp_path: Path) -> None:
        _write_approved(tmp_path, phase=1)
        base_url, port, server, thread = _start_dashboard(tmp_path)
        try:
            _, _, body = http_get(base_url, "/api/signoff", port=port)
            payload = json.loads(body.decode("utf-8"))
            assert payload["phases"]["1"]["state"] == SignoffState.APPROVED.value
        finally:
            _stop_dashboard(server, thread)

    def test_phase3_is_always_awaiting_signoff(self, tmp_path: Path) -> None:
        import sdlc.signoff.states as states_mod

        states_mod._phase3_warned = False
        base_url, port, server, thread = _start_dashboard(tmp_path)
        try:
            _, _, body = http_get(base_url, "/api/signoff", port=port)
            payload = json.loads(body.decode("utf-8"))
            assert payload["phases"]["3"]["state"] == SignoffState.AWAITING_SIGNOFF.value
        finally:
            _stop_dashboard(server, thread)

    def test_wire_values_are_byte_identical_to_signoff_state_enum(self, tmp_path: Path) -> None:
        """No translation table: the wire value equals SignoffState(...).value exactly."""
        _write_invalidated(tmp_path, phase=1, invalidated_at=_TS_INVAL)
        base_url, port, server, thread = _start_dashboard(tmp_path)
        try:
            _, _, body = http_get(base_url, "/api/signoff", port=port)
            payload = json.loads(body.decode("utf-8"))
            assert payload["phases"]["1"]["state"] in {s.value for s in SignoffState}
            assert payload["phases"]["1"]["state"] == "invalidated-by-replan"
        finally:
            _stop_dashboard(server, thread)


class TestInvalidatedByReplan:
    def test_invalidated_phase_reports_state_and_reason(self, tmp_path: Path) -> None:
        _write_invalidated(tmp_path, phase=2, invalidated_at=_TS_INVAL)
        base_url, port, server, thread = _start_dashboard(tmp_path)
        try:
            _, _, body = http_get(base_url, "/api/signoff", port=port)
            payload = json.loads(body.decode("utf-8"))
            entry = payload["phases"]["2"]
            assert entry["state"] == SignoffState.INVALIDATED_BY_REPLAN.value
            assert entry["invalidated_at"] == _TS_INVAL
            assert entry["invalidated_reason"] == "replan"
        finally:
            _stop_dashboard(server, thread)

    def test_invalidated_phase_surfaces_persisted_replan_scope(self, tmp_path: Path) -> None:
        _write_invalidated(tmp_path, phase=1, invalidated_at=_TS_INVAL)
        _append_replan_invalidated(
            tmp_path,
            ts=_TS_INVAL,
            scope="01-Requirement/PRODUCT.md",
            scope_phase=1,
            downstream_artifacts=["02-Architecture/ARCHITECTURE.md", "03-Implementation/PLAN.md"],
            reason="requirements changed after stakeholder review",
        )
        base_url, port, server, thread = _start_dashboard(tmp_path)
        try:
            _, _, body = http_get(base_url, "/api/signoff", port=port)
            payload = json.loads(body.decode("utf-8"))
            replan = payload["phases"]["1"]["replan"]
            assert replan["scope"] == "01-Requirement/PRODUCT.md"
            assert replan["scope_phase"] == 1
            assert replan["downstream_artifacts"] == [
                "02-Architecture/ARCHITECTURE.md",
                "03-Implementation/PLAN.md",
            ]
            assert replan["downstream_count"] == 2
            assert replan["reason"] == "requirements changed after stakeholder review"
        finally:
            _stop_dashboard(server, thread)

    def test_invalidated_phase_without_matching_journal_entry_omits_replan_key(
        self, tmp_path: Path
    ) -> None:
        """No matching replan_invalidated journal entry -> no fabricated 'replan' key."""
        _write_invalidated(tmp_path, phase=1, invalidated_at=_TS_INVAL)
        base_url, port, server, thread = _start_dashboard(tmp_path)
        try:
            _, _, body = http_get(base_url, "/api/signoff", port=port)
            payload = json.loads(body.decode("utf-8"))
            assert "replan" not in payload["phases"]["1"]
        finally:
            _stop_dashboard(server, thread)

    def test_approved_phase_never_carries_a_replan_key(self, tmp_path: Path) -> None:
        _write_approved(tmp_path, phase=1)
        base_url, port, server, thread = _start_dashboard(tmp_path)
        try:
            _, _, body = http_get(base_url, "/api/signoff", port=port)
            payload = json.loads(body.decode("utf-8"))
            assert "replan" not in payload["phases"]["1"]
        finally:
            _stop_dashboard(server, thread)


class TestFailLoud:
    def test_malformed_canonical_record_does_not_silently_demote(self, tmp_path: Path) -> None:
        """RED: a malformed record must propagate (fail-loud), never silently
        demote to awaiting-signoff — the server must NOT return 200 with a
        masked state for a corrupted phase-1.yaml."""
        signoff_dir = tmp_path / ".claude" / "state" / "signoffs"
        signoff_dir.mkdir(parents=True)
        (signoff_dir / "phase-1.yaml").write_text("}{bad yaml}{", encoding="utf-8")

        port = find_free_port()
        server, thread = serve_dashboard_in_thread(repo_root=tmp_path, port=port)
        base_url = f"http://127.0.0.1:{port}"
        try:
            with pytest.raises((OSError, ConnectionError)):
                # A 200-with-awaiting-signoff response would mean the malformed
                # record was silently demoted -- the connection must fail instead.
                http_get(base_url, "/api/signoff", port=port)
        finally:
            _stop_dashboard(server, thread)
