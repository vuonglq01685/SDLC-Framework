"""Stateful adopt / rollback / re-adopt sequence (Story 3.7, D6)."""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, settings
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

if sys.platform == "win32":  # pragma: no cover - adopt is POSIX-only (ADR-034)
    pytest.skip("adopt is POSIX-only (ADR-034)", allow_module_level=True)

from adopt._source_untouched_helpers import (
    AdoptInvocationMode,
    assert_source_tree_unchanged,
    copy_fixture,
    init_git_repo,
    run_adopt_for_mode,
    snapshot_source_bytes,
)
from sdlc.adopt.tree_hash import compute_source_tree_hash

pytestmark = pytest.mark.property


class _AdoptRollbackMachine(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self._tmpdir = Path(tempfile.mkdtemp(prefix="adopt-stateful-"))
        self.root = copy_fixture("java-maven-service", self._tmpdir)
        init_git_repo(self.root)
        self.legacy: tuple[str, ...] = ()
        self.before_hash = compute_source_tree_hash(self.root, legacy_code_globs=self.legacy)
        self.before_bytes = snapshot_source_bytes(self.root, legacy_code_globs=self.legacy)

    def teardown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    @invariant()
    def source_bytes_never_change(self) -> None:
        assert_source_tree_unchanged(
            self.root,
            before_hash=self.before_hash,
            before_bytes=self.before_bytes,
            legacy_code_globs=self.legacy,
        )

    @rule()
    def adopt(self) -> None:
        run_adopt_for_mode(self.root, AdoptInvocationMode.INTERACTIVE_ACCEPT_ALL)

    @rule()
    def rollback_redo(self) -> None:
        run_adopt_for_mode(self.root, AdoptInvocationMode.ROLLBACK_REDO)


TestAdoptRollbackMachine = _AdoptRollbackMachine.TestCase
TestAdoptRollbackMachine.settings = settings(
    max_examples=8,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
    stateful_step_count=4,
)
