"""AST gate tests for subprocess allow-list enforcement (Story 2B.6 AC2)."""

from __future__ import annotations

from pathlib import Path

import pytest

import check_subprocess_allowlist as sp_guard
from sdlc.errors import SecurityError

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_SDLC = _REPO_ROOT / "src" / "sdlc"
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
_FORBIDDEN_FIXTURE = _FIXTURES_DIR / "forbidden_subprocess.py"


@pytest.mark.unit
def test_forbidden_fixture_is_flagged() -> None:
    violations = sp_guard.scan_file(_FORBIDDEN_FIXTURE)
    assert len(violations) == 1
    first = violations[0]
    assert first.path == _FORBIDDEN_FIXTURE
    assert first.binary == "arbitrary"


@pytest.mark.unit
def test_violation_maps_to_security_error_exit_2() -> None:
    violation = sp_guard.scan_file(_FORBIDDEN_FIXTURE)[0]
    with pytest.raises(SecurityError) as exc_info:
        raise violation.to_security_error()
    assert exc_info.value.code == "ERR_SECURITY"
    assert exc_info.value.exit_code == 2


@pytest.mark.unit
def test_repo_src_scan_has_no_violations() -> None:
    assert sp_guard.main([str(_SRC_SDLC)]) == 0
