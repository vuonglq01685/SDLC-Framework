"""Abstraction-adequacy CI gate (Story 1.14 / Epic 1, extended Story 2B.3).

Runs the deterministic pipeline (init → scan → dispatch x2 → pre-write hook chain →
journal append → state projection → atomic state write) against MockAIRuntime and
ClaudeAIRuntime and asserts a golden HookPayload sequence and golden final state.json.

Contract (Story 2B.3): Mock and Claude produce IDENTICAL HookPayload sequences and
IDENTICAL final state.json bytes for the same input. Per-runtime golden asserts run
inside each parametrized body; mock-vs-claude byte identity is asserted by
``test_cross_runtime_byte_identity``, ordered after both parametrized runs via
``conftest.py``'s ``pytest_collection_modifyitems`` (AC2/D2).

POSIX-only: journal.append_sync + state.write_state_atomic_sync require fcntl + O_APPEND.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Final

import pytest

from integration._abstraction_adequacy_capture import pop_captured, record_runtime_bytes
from integration._abstraction_adequacy_helpers import (
    _ZERO_HASH,
    _build_journal_entry,
    _format_diff,
    _state_hash,
    dispatch_twice,
    fail_if_xdist_parallel,
    install_claude_stub_on_path,
    run_pre_write_hooks_for_dispatches,
)
from sdlc.engine import scan
from sdlc.journal import append_sync
from sdlc.runtime import AIRuntime, ClaudeAIRuntime, MockAIRuntime
from sdlc.state import write_state_atomic_sync
from sdlc.state.projection import project_from_journal

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason=(
            "POSIX-only: journal.append_sync + state.write_state_atomic_sync"
            " require fcntl + O_APPEND"
        ),
    ),
]

_REGENERATE_GOLDENS: Final[bool] = False

# Story 2B.10 AC9/D3=(a): Phase-3 conformance representative.
# code-author (GREEN phase, TDD pipeline) is pinned as the Phase-3 specialist exercised
# by the 2B.3 mock-vs-claude byte-identity contract. Phase-3 markdown authoring adds no
# new Python dispatch logic — no golden regeneration is needed. The Phase-3 registry is
# independently verified in tests/unit/specialists/test_phase3_2b10_authoring.py.
_PHASE3_CONFORMANCE_REPRESENTATIVE: Final[str] = "code-author"

_TESTS_DIR: Final[Path] = Path(__file__).resolve().parent.parent
_GOLDEN_DIR: Final[Path] = _TESTS_DIR / "fixtures" / "abstraction_adequacy"
_SEED_FIXTURE_NAME: Final[str] = "abstraction-adequacy.yaml"
_SOURCE_FIXTURE: Final[Path] = _TESTS_DIR / "fixtures" / "mock_responses" / _SEED_FIXTURE_NAME


def _mock_factory(fixtures_dir: Path) -> AIRuntime:
    return MockAIRuntime(fixtures_dir=fixtures_dir)


def _claude_factory(fixtures_dir: Path) -> AIRuntime:
    del fixtures_dir
    return ClaudeAIRuntime()


# EPIC 2B GATE — Story 2B.3 extended this list to [_mock_factory, _claude_factory].
# Both factories MUST produce identical HookPayload sequences and identical final state.json
# bytes (Decision C2, Architecture §1424, FR29).
# DO NOT add a third factory in v1.
_RUNTIME_FACTORIES: list[Callable[[Path], AIRuntime]] = [_mock_factory, _claude_factory]

# Parametrization ids, derived from the factories (review P3): a factory rename stays in sync
# with the cross-runtime identity check instead of drifting from hardcoded string keys.
_FACTORY_IDS: Final[tuple[str, ...]] = tuple(f.__name__.lstrip("_") for f in _RUNTIME_FACTORIES)


@pytest.fixture
def isolated_fixtures_dir(tmp_path: Path) -> Path:
    """Per-test fixtures directory containing ONLY the abstraction-adequacy seed."""
    isolated = tmp_path / "fixtures"
    isolated.mkdir(parents=True, exist_ok=False)
    shutil.copy2(_SOURCE_FIXTURE, isolated / _SEED_FIXTURE_NAME)
    return isolated


@pytest.fixture(
    params=_RUNTIME_FACTORIES,
    ids=lambda factory: factory.__name__.lstrip("_"),
)
def runtime(
    request: pytest.FixtureRequest,
    isolated_fixtures_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AIRuntime:
    fail_if_xdist_parallel(request.config)
    factory: Callable[[Path], AIRuntime] = request.param
    if factory is _claude_factory:
        install_claude_stub_on_path(
            monkeypatch,
            isolated_fixtures_dir / _SEED_FIXTURE_NAME,
            tmp_path,
        )
    return factory(isolated_fixtures_dir)


def test_abstraction_adequacy_pipeline(
    tmp_path: Path,
    runtime: AIRuntime,
    request: pytest.FixtureRequest,
) -> None:
    # Drop the "runtime" fallback (review P5): this test is only meaningful when run
    # parametrized via the runtime fixture; a missing callspec means misconfiguration.
    assert request.node.callspec is not None, (
        "test_abstraction_adequacy_pipeline must run parametrized via the `runtime` fixture"
    )
    factory_id = request.node.callspec.id
    state_dir = tmp_path / ".claude" / "state"
    state_dir.mkdir(parents=True, exist_ok=False)
    journal_path = state_dir / "journal.log"
    state_path = state_dir / "state.json"

    initial_state = scan(tmp_path)
    assert project_from_journal(journal_path) == initial_state

    # One asyncio.run wrapping two awaited dispatches — see dispatch_twice() for why two
    # separate asyncio.run calls would trip the loop-teardown DeprecationWarning (P25).
    result_1, result_2 = asyncio.run(dispatch_twice(runtime))
    assert result_1.model_dump(mode="json") == result_2.model_dump(mode="json"), (
        "non-deterministic dispatch — Story 1.13 AC3 violated"
    )

    hook_payloads = asyncio.run(
        run_pre_write_hooks_for_dispatches(
            repo_root=tmp_path,
            journal_path=journal_path,
            results=(result_1, result_2),
        )
    )

    je_0 = _build_journal_entry(
        seq=0,
        before_hash=None,
        after_hash=_ZERO_HASH,
        agent_result=result_1,
    )
    append_sync(je_0, journal_path=journal_path)
    je_1 = _build_journal_entry(
        seq=1,
        before_hash=je_0.after_hash,
        after_hash="sha256:1111111111111111111111111111111111111111111111111111111111111111",
        agent_result=result_2,
    )
    append_sync(je_1, journal_path=journal_path)
    assert je_1.before_hash == hook_payloads[1].content_hash_before, (
        "hash chain decoupled from hook payload — see _REGENERATE_GOLDENS docs"
    )

    final_state = project_from_journal(journal_path)
    final_hash = _state_hash(final_state)
    assert final_hash.startswith("sha256:")
    assert _state_hash(final_state) == final_hash, "_state_hash is non-deterministic"

    write_state_atomic_sync(final_state, target=state_path)

    actual_hp_bytes = (
        json.dumps(
            [hp.model_dump(mode="json") for hp in hook_payloads],
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    actual_state_bytes = state_path.read_bytes()

    if _REGENERATE_GOLDENS:
        _GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        (_GOLDEN_DIR / "expected_hook_payloads.json").write_bytes(actual_hp_bytes)
        (_GOLDEN_DIR / "expected_state.json").write_bytes(actual_state_bytes)
        pytest.fail(
            "_REGENERATE_GOLDENS=True wrote new goldens; flip back to False"
            " and verify diff before committing.",
            pytrace=False,
        )

    # Capture BEFORE the per-runtime golden asserts (review P4): the cross-runtime identity
    # check (test_cross_runtime_byte_identity) must observe both runtimes' bytes even when a
    # per-runtime golden assert fails. A common drift (both runtimes diverge from the golden
    # the same way) would otherwise be hidden behind whichever runtime's golden-mismatch ran
    # first, masking the mock-vs-claude delta this gate exists to surface.
    record_runtime_bytes(factory_id, actual_hp_bytes, actual_state_bytes)

    expected_hp_bytes = (_GOLDEN_DIR / "expected_hook_payloads.json").read_bytes()
    expected_state_bytes = (_GOLDEN_DIR / "expected_state.json").read_bytes()
    assert actual_hp_bytes == expected_hp_bytes, _format_diff(
        "hook payloads vs golden", expected_hp_bytes, actual_hp_bytes
    )
    assert actual_state_bytes == expected_state_bytes, _format_diff(
        "state.json vs golden", expected_state_bytes, actual_state_bytes
    )


def test_cross_runtime_byte_identity(request: pytest.FixtureRequest) -> None:
    """AC2/D2: mock and claude produce byte-identical hook payloads AND state.json.

    This is the cross-run assertion. It is a regular test (NOT a ``pytest_sessionfinish``
    hook — review P30 / D1=b) so a divergence reports as a normal test failure with a unified
    diff, not a version-dependent INTERNALERROR. ``conftest.py``'s
    ``pytest_collection_modifyitems`` orders this test AFTER both parametrized
    ``test_abstraction_adequacy_pipeline`` runs so the capture registry is fully populated.
    """
    fail_if_xdist_parallel(request.config)
    captured = pop_captured()
    missing = [fid for fid in _FACTORY_IDS if fid not in captured]
    assert not missing, (
        f"cross-runtime identity check is missing captures for {missing}; expected one per "
        f"runtime factory {list(_FACTORY_IDS)} (captured: {sorted(captured)}). Did the "
        "parametrized pipeline runs execute, and is the test ordered last?"
    )
    # Exactly two factories (the "DO NOT add a third factory in v1" invariant). Unpacking two
    # ids fails loud if a third factory is ever added without revisiting this check.
    first_id, second_id = _FACTORY_IDS
    first_hp, first_state = captured[first_id]
    second_hp, second_state = captured[second_id]
    assert first_hp == second_hp, _format_diff(
        f"hook payloads ({first_id} vs {second_id})", first_hp, second_hp
    )
    assert first_state == second_state, _format_diff(
        f"state.json ({first_id} vs {second_id})", first_state, second_state
    )


def test_phase3_conformance_representative_registered() -> None:
    """Story 2B.10 AC9/D3=(a): code-author is registered as Phase-3 conformance rep.

    Verifies the Phase-3 representative specialist is loadable via load_registry and
    that Phase-3 authoring did not disturb the conformance pipeline golden outputs
    (the three parametrized / cross-runtime tests above remain the byte-identity gate).
    """
    from pathlib import Path

    from sdlc.specialists import load_registry

    agents_dir = Path(__file__).resolve().parents[2] / "src" / "sdlc" / "agents"
    reg = load_registry(agents_dir)
    s = reg.get(_PHASE3_CONFORMANCE_REPRESENTATIVE)
    assert s.phase == 3, (
        f"Phase-3 conformance representative {_PHASE3_CONFORMANCE_REPRESENTATIVE!r} "
        f"has phase={s.phase}, expected 3"
    )
    assert s.frontmatter.schema_version == 1
    assert s.frontmatter.name == _PHASE3_CONFORMANCE_REPRESENTATIVE


# To regenerate goldens (e.g., after a deliberate fixture change):
#   1. Set _REGENERATE_GOLDENS = True at the top of this file.
#   2. uv run pytest tests/integration/test_abstraction_adequacy.py -m integration
#      (must run on Linux/macOS — POSIX-only; Windows skips this test)
#   3. The test will WRITE the goldens instead of asserting; visually diff the result.
#   4. Set _REGENERATE_GOLDENS = False; commit the new goldens with a justifying message.
# DO NOT regenerate goldens to make a failing test pass without first auditing
# WHY the bytes drifted — drift is the symptom this test exists to catch.
