"""Playwright behavioral contracts for the Phase Tracker real-signoff poller (Story 5.14).

Executes the real `/api/signoff` route + `phase-tracker-live.js` poller in a
browser DOM (mirrors the 5.11 activity-feed incremental-render witness,
``tests/integration/test_dashboard_activity_feed_empty_state.py``) — the
static-source contract in
``tests/unit/dashboard/test_phase_tracker_live_source.py`` cannot MEASURE
actual rendered state, DOM node identity across a poll, or the click-through
disclosure.

Covers:
  AC1        — real per-phase signoff renders on the 5.9 cells + the next
               poll cycle (3 s) reflects a state transition.
  NFR-PERF-4 — only-changed re-render: sibling cells retain DOM node identity.
  AC2 / D2   — invalidated-by-replan renders the red `slash-circle` +
               "INVALIDATED" label and the click-through reveals the
               persisted replan scope with no modal/dialog element.
"""

from __future__ import annotations

import textwrap
import time
import urllib.request
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from sdlc.dashboard.server import find_free_port, serve_dashboard_in_thread
from sdlc.journal.writer import allocate_next_seq_for_append_sync, append_sync
from sdlc.signoff.records import ArtifactRef, SignoffRecord, write_record

pytest.importorskip("playwright")

pytestmark = pytest.mark.integration

_FIXTURE = "/static/components/phase-tracker/phase-tracker-live.fixture.html"
_TRACKER = "#phase-tracker-live"
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


def _write_approved(repo_root: Path, phase: int) -> None:
    record = SignoffRecord(
        phase=phase,
        artifacts=(ArtifactRef(path=f"{_PHASE_DIR[phase]}/PRODUCT.md", hash=_VALID_HASH),),
        approved_by="alice",
        approved_at=_TS2,
        drafted_at=_TS1,
        validated_at=_TS2,
    )
    write_record(record, repo_root=repo_root)


def _write_invalidated(repo_root: Path, phase: int) -> None:
    from sdlc.contracts.journal_entry import JournalEntry
    from sdlc.signoff.records import _canonicalize_record, _signoff_path, _write_bytes_to_disk

    record = SignoffRecord(
        phase=phase,
        artifacts=(ArtifactRef(path=f"{_PHASE_DIR[phase]}/PRODUCT.md", hash=_VALID_HASH),),
        approved_by="alice",
        approved_at=_TS2,
        drafted_at=_TS1,
        validated_at=_TS2,
        invalidated_at=_TS_INVAL,
        invalidated_reason="replan",
    )
    _write_bytes_to_disk(_signoff_path(phase, repo_root), _canonicalize_record(record))

    journal_path = repo_root / _JOURNAL_REL
    seq = allocate_next_seq_for_append_sync(journal_path)
    entry = JournalEntry(
        monotonic_seq=seq,
        ts=_TS_INVAL,
        kind="replan_invalidated",
        actor="cli:replan",
        target_id=f"{_PHASE_DIR[phase]}/PRODUCT.md",
        before_hash=None,
        after_hash=_VALID_HASH,
        payload={
            "scope": f"{_PHASE_DIR[phase]}/PRODUCT.md",
            "scope_phase": phase,
            "downstream_artifacts": ["02-Architecture/ARCHITECTURE.md"],
            "downstream_count": 1,
            "reason": "requirements changed after stakeholder review",
        },
    )
    append_sync(entry, journal_path=journal_path)


@pytest.fixture()
def dashboard(tmp_path: Path) -> Generator[tuple[str, Path], None, None]:
    (tmp_path / ".claude" / "state").mkdir(parents=True)
    port = find_free_port()
    server, thread = serve_dashboard_in_thread(repo_root=tmp_path, port=port)
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}{_FIXTURE}", timeout=1) as resp:
                if resp.status == 200:
                    break
        except OSError:
            time.sleep(0.05)
    else:
        pytest.fail("dashboard server did not become ready")
    yield base_url, tmp_path
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


@contextmanager
def _with_playwright_page(url: str) -> Iterator[object]:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except PlaywrightError as exc:
            pytest.skip(f"Playwright Chromium not installed: {exc}")
        try:
            page = browser.new_page()
            page.goto(url, wait_until="networkidle")
            page.wait_for_selector(f"{_TRACKER} signoff-cell[data-phase='1']")
            yield page
        finally:
            browser.close()


class TestRealStateRendering:
    def test_initial_render_reflects_real_signoff_state(self, dashboard: tuple[str, Path]) -> None:
        base_url, repo_root = dashboard
        _write_approved(repo_root, phase=1)
        _write_draft(repo_root, phase=2)
        with _with_playwright_page(f"{base_url}{_FIXTURE}") as page:
            page.wait_for_function(
                f"""() => document.querySelector({_TRACKER + " signoff-cell[data-phase='1']"!r})
                    .getAttribute('state') === 'approved'""",
                timeout=5_000,
            )
            state2 = page.get_attribute(f"{_TRACKER} signoff-cell[data-phase='2']", "state")
            state3_row = page.get_attribute(f"{_TRACKER} phase-item-row[data-phase='3']", "state")
            assert state2 == "drafted-not-approved"
            assert state3_row == "awaiting-signoff"

    def test_state_transition_appears_on_next_poll_cycle(self, dashboard: tuple[str, Path]) -> None:
        """AC1 final-And: a state transition on disk appears within the next 3 s poll."""
        base_url, repo_root = dashboard
        with _with_playwright_page(f"{base_url}{_FIXTURE}") as page:
            page.wait_for_function(
                f"""() => document.querySelector({_TRACKER + " signoff-cell[data-phase='2']"!r})
                    .getAttribute('state') === 'awaiting-signoff'""",
                timeout=5_000,
            )
            _write_draft(repo_root, phase=2)
            page.wait_for_function(
                f"""() => document.querySelector({_TRACKER + " signoff-cell[data-phase='2']"!r})
                    .getAttribute('state') === 'drafted-not-approved'""",
                timeout=6_000,
            )


class TestOnlyChangedRerender:
    def test_applying_a_snapshot_preserves_sibling_dom_node_identity(
        self, dashboard: tuple[str, Path]
    ) -> None:
        """NFR-PERF-4/DD-06: only the changed cell's node is touched; siblings +
        the grid container itself keep their existing DOM node identity — no
        full grid resynthesis."""
        base_url, _repo_root = dashboard
        with _with_playwright_page(f"{base_url}{_FIXTURE}") as page:
            result = page.evaluate(
                f"""async () => {{
                    const mod = await import(
                        '/static/components/phase-tracker/phase-tracker-live.js'
                    );
                    const root = document.querySelector({_TRACKER!r});
                    const grid = root.querySelector('.phase-tracker__grid');
                    const allNodes = [...root.querySelectorAll('*'), grid];
                    allNodes.forEach((el) => {{ el.dataset.witness = 'keep'; }});

                    mod.applySignoffSnapshot(root, {{
                        phases: {{
                            '1': {{
                                state: 'approved',
                                invalidated_at: null,
                                invalidated_reason: null,
                            }},
                            '2': {{
                                state: 'awaiting-signoff',
                                invalidated_at: null,
                                invalidated_reason: null,
                            }},
                            '3': {{
                                state: 'awaiting-signoff',
                                invalidated_at: null,
                                invalidated_reason: null,
                            }},
                        }},
                    }});

                    return {{
                        gridStillSameNode: grid.dataset.witness === 'keep',
                        phase1State: root
                            .querySelector('signoff-cell[data-phase="1"]')
                            .getAttribute('state'),
                        phase1RowState: root
                            .querySelector('phase-item-row[data-phase="1"]')
                            .getAttribute('state'),
                        phase2Untouched: root
                            .querySelector('signoff-cell[data-phase="2"]')
                            .dataset.witness === 'keep',
                        phase3Untouched: root
                            .querySelector('phase-item-row[data-phase="3"]')
                            .dataset.witness === 'keep',
                    }};
                }}"""
            )
            assert result["gridStillSameNode"], "grid container must not be replaced"
            assert result["phase1State"] == "approved"
            assert result["phase1RowState"] == "approved"
            assert result["phase2Untouched"], "unchanged sibling cell must keep its DOM node"
            assert result["phase3Untouched"], "unchanged sibling row must keep its DOM node"

    def test_reapplying_the_same_snapshot_does_not_rewrite_unchanged_attributes(
        self, dashboard: tuple[str, Path]
    ) -> None:
        base_url, _repo_root = dashboard
        with _with_playwright_page(f"{base_url}{_FIXTURE}") as page:
            changed_count = page.evaluate(
                f"""async () => {{
                    const mod = await import(
                        '/static/components/phase-tracker/phase-tracker-live.js'
                    );
                    const root = document.querySelector({_TRACKER!r});
                    const nullDetail = {{ invalidated_at: null, invalidated_reason: null }};
                    const snapshot = {{
                        phases: {{
                            '1': {{ state: 'awaiting-signoff', ...nullDetail }},
                            '2': {{ state: 'awaiting-signoff', ...nullDetail }},
                            '3': {{ state: 'awaiting-signoff', ...nullDetail }},
                        }},
                    }};
                    mod.applySignoffSnapshot(root, snapshot);
                    // Second apply with an IDENTICAL snapshot must report no change.
                    return mod.applySignoffSnapshot(root, snapshot);
                }}"""
            )
            assert changed_count is False, "re-applying an identical snapshot must be a no-op"


class TestInvalidatedByReplanClickThrough:
    def test_invalidated_phase_renders_red_slash_circle_and_text_label(
        self, dashboard: tuple[str, Path]
    ) -> None:
        base_url, repo_root = dashboard
        _write_invalidated(repo_root, phase=1)
        with _with_playwright_page(f"{base_url}{_FIXTURE}") as page:
            page.wait_for_function(
                f"""() => document.querySelector({_TRACKER + " signoff-cell[data-phase='1']"!r})
                    .getAttribute('state') === 'invalidated-by-replan'""",
                timeout=5_000,
            )
            data = page.evaluate(
                f"""() => {{
                    const cell = document.querySelector(
                        {_TRACKER + " signoff-cell[data-phase='1']"!r}
                    );
                    return {{
                        label: cell.querySelector('.signoff-cell__state-label').textContent,
                        glyphHref: cell.querySelector('use').getAttribute('href'),
                    }};
                }}"""
            )
            assert data["label"] == "INVALIDATED"
            assert data["glyphHref"].endswith("#slash-circle")

    def test_click_through_reveals_replan_scope_without_modal(
        self, dashboard: tuple[str, Path]
    ) -> None:
        base_url, repo_root = dashboard
        _write_invalidated(repo_root, phase=1)
        with _with_playwright_page(f"{base_url}{_FIXTURE}") as page:
            page.wait_for_function(
                f"""() => document.querySelector({_TRACKER + " signoff-cell[data-phase='1']"!r})
                    .getAttribute('state') === 'invalidated-by-replan'""",
                timeout=5_000,
            )
            page.click(f"{_TRACKER} signoff-cell[data-phase='1']")
            page.wait_for_selector(
                f"{_TRACKER} [data-role='replan-detail'][data-phase='1']:not([hidden])"
            )
            detail_text = page.inner_text(f"{_TRACKER} [data-role='replan-detail'][data-phase='1']")
            assert "requirements changed after stakeholder review" in detail_text
            assert "02-Architecture/ARCHITECTURE.md" in detail_text

            no_modal = page.evaluate(
                """() => ({
                    dialogCount: document.querySelectorAll('dialog').length,
                    roleDialogCount: document.querySelectorAll('[role="dialog"]').length,
                    toastCount: document.querySelectorAll('[class*="toast" i]').length,
                })"""
            )
            assert no_modal["dialogCount"] == 0
            assert no_modal["roleDialogCount"] == 0
            assert no_modal["toastCount"] == 0

    def test_approved_phase_click_does_not_reveal_any_detail(
        self, dashboard: tuple[str, Path]
    ) -> None:
        base_url, repo_root = dashboard
        _write_approved(repo_root, phase=1)
        with _with_playwright_page(f"{base_url}{_FIXTURE}") as page:
            page.wait_for_function(
                f"""() => document.querySelector({_TRACKER + " signoff-cell[data-phase='1']"!r})
                    .getAttribute('state') === 'approved'""",
                timeout=5_000,
            )
            page.click(f"{_TRACKER} signoff-cell[data-phase='1']")
            hidden = page.get_attribute(
                f"{_TRACKER} [data-role='replan-detail'][data-phase='1']", "hidden"
            )
            assert hidden is not None, "an approved (non-invalidated) cell must not disclose"
