"""AST gate tests for forbidden outbound-network imports (Story 2B.6 AC1)."""

from __future__ import annotations

from pathlib import Path

import pytest

import check_no_outbound_http as net_guard
from sdlc.errors import SecurityError

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
_FORBIDDEN_FIXTURE = _FIXTURES_DIR / "forbidden_net_import.py"
_CLEAN_FIXTURE = _FIXTURES_DIR / "clean_local_module.py"


@pytest.mark.unit
def test_forbidden_fixture_is_flagged_with_file_line_and_module() -> None:
    violations = net_guard.scan_file(_FORBIDDEN_FIXTURE)
    assert len(violations) == 1
    first = violations[0]
    assert first.path == _FORBIDDEN_FIXTURE
    assert first.line >= 1
    assert first.module == "requests"


@pytest.mark.unit
def test_clean_fixture_has_no_violations() -> None:
    assert net_guard.scan_file(_CLEAN_FIXTURE) == []


@pytest.mark.unit
def test_violation_to_security_error_uses_err_security_exit_2() -> None:
    violation = net_guard.scan_file(_FORBIDDEN_FIXTURE)[0]
    with pytest.raises(SecurityError) as exc_info:
        raise violation.to_security_error()
    assert exc_info.value.code == "ERR_SECURITY"
    assert exc_info.value.exit_code == 2
