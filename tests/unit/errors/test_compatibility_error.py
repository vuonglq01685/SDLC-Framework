"""Unit tests for CompatibilityError (Story 2B.2, AC1/D2)."""

from __future__ import annotations

import pytest

from sdlc.errors import EXIT_CODE_MAP, CompatibilityError, SdlcError


@pytest.mark.unit
class TestCompatibilityError:
    def test_is_subclass_of_sdlc_error(self) -> None:
        assert issubclass(CompatibilityError, SdlcError)

    def test_code_is_err_compatibility(self) -> None:
        assert CompatibilityError.code == "ERR_COMPATIBILITY"

    def test_exit_code_is_3(self) -> None:
        assert CompatibilityError("msg").exit_code == 3

    def test_exit_code_map_registers_err_compatibility(self) -> None:
        assert EXIT_CODE_MAP["ERR_COMPATIBILITY"] == 3

    def test_importable_from_sdlc_errors(self) -> None:
        from sdlc.errors import CompatibilityError as CE

        assert CE is CompatibilityError
