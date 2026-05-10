"""Assert check_module_boundaries.py knows about the workflows/ module (Story 2A.1, AC8)."""

from __future__ import annotations

import pytest

import check_module_boundaries as guard


@pytest.mark.unit
class TestWorkflowsModuleBoundaries:
    def test_workflows_in_module_deps(self) -> None:
        assert "workflows" in guard.MODULE_DEPS

    def test_workflows_depends_on_errors(self) -> None:
        assert "errors" in guard.MODULE_DEPS["workflows"].depends_on

    def test_workflows_depends_on_contracts(self) -> None:
        assert "contracts" in guard.MODULE_DEPS["workflows"].depends_on

    def test_workflows_depends_on_ids(self) -> None:
        assert "ids" in guard.MODULE_DEPS["workflows"].depends_on

    def test_workflows_forbidden_from_engine(self) -> None:
        assert "engine" in guard.MODULE_DEPS["workflows"].forbidden_from

    def test_workflows_forbidden_from_dispatcher(self) -> None:
        assert "dispatcher" in guard.MODULE_DEPS["workflows"].forbidden_from

    def test_workflows_forbidden_from_runtime(self) -> None:
        assert "runtime" in guard.MODULE_DEPS["workflows"].forbidden_from
