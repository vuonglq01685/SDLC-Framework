"""Unit tests for WorkflowError (Story 2A.1, AC7)."""

from __future__ import annotations

import pytest

from sdlc.errors import SdlcError, WorkflowError


@pytest.mark.unit
class TestWorkflowError:
    def test_is_subclass_of_sdlc_error(self) -> None:
        assert issubclass(WorkflowError, SdlcError)

    def test_message_round_trip(self) -> None:
        err = WorkflowError("workflow parse failed")
        assert str(err) == "workflow parse failed"
        assert err.message == "workflow parse failed"

    def test_details_round_trip(self) -> None:
        err = WorkflowError("bad field", details={"path": "foo.yaml", "field": "name"})
        assert err.details["path"] == "foo.yaml"
        assert err.details["field"] == "name"

    def test_details_defaults_to_empty_dict(self) -> None:
        err = WorkflowError("msg")
        assert err.details == {}

    def test_isinstance_of_sdlc_error(self) -> None:
        err = WorkflowError("msg")
        assert isinstance(err, SdlcError)

    def test_importable_from_sdlc_errors(self) -> None:
        from sdlc.errors import WorkflowError as WE

        assert WE is WorkflowError

    def test_code_is_err_workflow(self) -> None:
        assert WorkflowError.code == "ERR_WORKFLOW"

    def test_not_subclass_of_schema_error(self) -> None:
        from sdlc.errors import SchemaError

        assert not issubclass(WorkflowError, SchemaError)
