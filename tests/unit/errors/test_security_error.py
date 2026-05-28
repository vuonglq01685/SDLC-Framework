"""Unit tests for SecurityError (Story 2B.5, AC2/D1)."""

from __future__ import annotations

import pytest

from sdlc.errors import EXIT_CODE_MAP, SdlcError, SecurityError


@pytest.mark.unit
class TestSecurityError:
    def test_is_subclass_of_sdlc_error(self) -> None:
        assert issubclass(SecurityError, SdlcError)

    def test_code_is_err_security(self) -> None:
        assert SecurityError.code == "ERR_SECURITY"

    def test_exit_code_is_2(self) -> None:
        assert SecurityError("msg").exit_code == 2

    def test_exit_code_map_registers_err_security(self) -> None:
        assert EXIT_CODE_MAP["ERR_SECURITY"] == 2

    def test_importable_from_sdlc_errors(self) -> None:
        from sdlc.errors import SecurityError as SE

        assert SE is SecurityError
