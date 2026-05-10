from __future__ import annotations

import pytest

from sdlc.errors import SdlcError, SpecialistError


@pytest.mark.unit
def test_specialist_error_is_subclass_of_sdlc_error() -> None:
    assert issubclass(SpecialistError, SdlcError)


@pytest.mark.unit
def test_specialist_error_is_direct_subclass_only() -> None:
    # Must be a direct subclass of SdlcError — NOT SchemaError, NOT WorkflowError.
    assert SpecialistError.__bases__ == (SdlcError,)


@pytest.mark.unit
def test_specialist_error_message_round_trip() -> None:
    err = SpecialistError("missing agent index.yaml")
    assert str(err) == "missing agent index.yaml"
    assert err.message == "missing agent index.yaml"


@pytest.mark.unit
def test_specialist_error_details_round_trip() -> None:
    err = SpecialistError(
        "bad frontmatter", details={"path": "agents/foo.md", "hint": "check name"}
    )
    assert err.details == {"path": "agents/foo.md", "hint": "check name"}


@pytest.mark.unit
def test_specialist_error_details_defaults_to_empty_dict() -> None:
    err = SpecialistError("orphan specialist")
    assert err.details == {}


@pytest.mark.unit
def test_specialist_error_importable_from_sdlc_errors() -> None:
    # Import path must be `from sdlc.errors import SpecialistError`.
    from sdlc.errors import SpecialistError as _SE

    assert _SE is SpecialistError


@pytest.mark.unit
def test_specialist_error_to_envelope_includes_code() -> None:
    err = SpecialistError("test")
    envelope = err.to_envelope()
    assert envelope["error"]["code"] == "ERR_SPECIALIST"  # type: ignore[index]
