from __future__ import annotations

import json

import pytest

from sdlc.errors import (
    EXIT_CODE_MAP,
    AdoptError,
    CompatibilityError,
    ConfigError,
    DispatchError,
    HookError,
    IdsError,
    JournalError,
    MockMissError,
    SchemaError,
    SdlcError,
    SignoffError,
    StateError,
)

_ALL_SUBCLASSES = [
    StateError,
    JournalError,
    DispatchError,
    HookError,
    SchemaError,
    SignoffError,
    AdoptError,
    ConfigError,
    IdsError,
    CompatibilityError,
]


@pytest.mark.unit
def test_sdlc_error_instantiates_with_message_only() -> None:
    err = SdlcError("something failed")
    assert err.message == "something failed"
    assert err.details == {}


@pytest.mark.unit
def test_sdlc_error_instantiates_with_details() -> None:
    err = SdlcError("something failed", details={"path": "/tmp/state.json"})
    assert err.details == {"path": "/tmp/state.json"}


@pytest.mark.unit
def test_details_default_is_not_shared_across_instances() -> None:
    err1 = SdlcError("first")
    err2 = SdlcError("second")
    err1.details["injected"] = True
    assert "injected" not in err2.details


@pytest.mark.unit
def test_details_defensive_copy_from_caller_dict() -> None:
    original = {"key": "value"}
    err = SdlcError("test", details=original)
    original["key"] = "mutated"
    assert err.details["key"] == "value"


@pytest.mark.unit
@pytest.mark.parametrize("cls", _ALL_SUBCLASSES)
def test_subclass_instantiates_with_message(cls: type[SdlcError]) -> None:
    err = cls("msg")
    assert err.message == "msg"
    assert err.details == {}


@pytest.mark.unit
@pytest.mark.parametrize("cls", _ALL_SUBCLASSES)
def test_subclass_instantiates_with_details(cls: type[SdlcError]) -> None:
    err = cls("msg", details={"path": "/tmp"})
    assert err.details == {"path": "/tmp"}


@pytest.mark.unit
@pytest.mark.parametrize("cls", _ALL_SUBCLASSES)
def test_subclass_is_instance_of_sdlc_error(cls: type[SdlcError]) -> None:
    err = cls("msg")
    assert isinstance(err, SdlcError)


@pytest.mark.unit
@pytest.mark.parametrize("cls", _ALL_SUBCLASSES)
def test_str_returns_message(cls: type[SdlcError]) -> None:
    err = cls("boom")
    assert str(err) == "boom"


@pytest.mark.unit
@pytest.mark.parametrize("cls", _ALL_SUBCLASSES)
def test_repr_includes_class_name(cls: type[SdlcError]) -> None:
    err = cls("boom")
    assert cls.__name__ in repr(err)


@pytest.mark.unit
def test_exit_code_map_size_matches_subclass_count() -> None:
    assert len(EXIT_CODE_MAP) == len(_ALL_SUBCLASSES)


@pytest.mark.unit
def test_exit_code_map_covers_all_concrete_subclasses() -> None:
    for cls in _ALL_SUBCLASSES:
        assert cls.code in EXIT_CODE_MAP, (
            f"{cls.__name__}.code={cls.code!r} missing from EXIT_CODE_MAP"
        )


@pytest.mark.unit
def test_config_error_exit_code_is_1() -> None:
    assert ConfigError("x").exit_code == 1


@pytest.mark.unit
def test_ids_error_exit_code_is_1() -> None:
    assert IdsError("x").exit_code == 1


@pytest.mark.unit
def test_compatibility_error_exit_code_is_3() -> None:
    assert CompatibilityError("x").exit_code == 3


@pytest.mark.unit
@pytest.mark.parametrize(
    "cls",
    [StateError, JournalError, DispatchError, HookError, SchemaError, SignoffError, AdoptError],
)
def test_framework_errors_exit_code_is_2(cls: type[SdlcError]) -> None:
    assert cls("x").exit_code == 2


@pytest.mark.unit
def test_sdlc_error_root_exit_code_defaults_to_2() -> None:
    # SdlcError.code = "ERR_SDLC" is not in EXIT_CODE_MAP → defaults to 2
    assert SdlcError("x").exit_code == 2


@pytest.mark.unit
@pytest.mark.parametrize("cls", _ALL_SUBCLASSES)
def test_to_envelope_shape(cls: type[SdlcError]) -> None:
    err = cls("oops", details={"key": "val"})
    envelope = err.to_envelope()
    assert set(envelope.keys()) == {"error"}
    inner = envelope["error"]
    assert isinstance(inner, dict)
    inner_dict = dict(inner)  # type: ignore[arg-type]
    assert set(inner_dict.keys()) == {"code", "message", "details", "exit_code"}
    assert inner_dict["code"] == cls.code
    assert inner_dict["message"] == "oops"
    assert inner_dict["details"] == {"key": "val"}
    assert inner_dict["exit_code"] == err.exit_code


@pytest.mark.unit
@pytest.mark.parametrize("cls", _ALL_SUBCLASSES)
def test_to_envelope_is_json_serializable(cls: type[SdlcError]) -> None:
    err = cls("oops", details={"n": 42})
    envelope = err.to_envelope()
    json.dumps(envelope)  # must not raise


@pytest.mark.unit
def test_mock_miss_error_inherits_dispatch_error_code() -> None:
    e = MockMissError("test fixture missing")
    assert e.code == "ERR_DISPATCH"
    assert e.exit_code == 2
    assert e.to_envelope()["error"]["code"] == "ERR_DISPATCH"


@pytest.mark.unit
def test_mock_miss_error_is_dispatch_error() -> None:
    e = MockMissError("test")
    assert isinstance(e, DispatchError)
    assert isinstance(e, SdlcError)


@pytest.mark.unit
def test_mock_miss_error_accepts_details() -> None:
    e = MockMissError("miss", details={"step": "fixture_lookup", "workflow_step": "sdlc-epics"})
    assert e.details["step"] == "fixture_lookup"
    assert e.details["workflow_step"] == "sdlc-epics"
