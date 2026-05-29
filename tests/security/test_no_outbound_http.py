"""AST gate tests for forbidden outbound-network imports (Story 2B.6 AC1)."""

from __future__ import annotations

from pathlib import Path

import pytest

import check_no_outbound_http as net_guard
from sdlc.errors import SecurityError

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
_FORBIDDEN_FIXTURE = _FIXTURES_DIR / "forbidden_net_import.py"
_CLEAN_FIXTURE = _FIXTURES_DIR / "clean_local_module.py"
_NOQA_EXEMPT_FIXTURE = _FIXTURES_DIR / "noqa_exempt_net_import.py"


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


# ---------------------------------------------------------------------------
# Post-review hardening (2026-05-28 bmad-code-review)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_noqa_exempt_fixture_has_no_violations_p23() -> None:
    """P23 anti-tautology receipt: the ``# noqa: net -- <reason>`` exemption
    path is load-bearing — a fixture that DOES import a forbidden module but
    carries the marker MUST produce zero violations."""
    assert net_guard.scan_file(_NOQA_EXEMPT_FIXTURE) == []


@pytest.mark.unit
def test_dynamic_importlib_call_is_flagged_p17() -> None:
    """P17: ``importlib.import_module('requests')`` is detected even though
    it bypasses ``ast.Import`` / ``ast.ImportFrom``."""
    import textwrap

    source = textwrap.dedent(
        """
        import importlib
        importlib.import_module("requests")
        """
    )
    tree = net_guard.ast.parse(source)
    violations = [
        v for node in net_guard.ast.walk(tree) for v in net_guard._check_node(node, Path("dyn.py"))
    ]
    assert any(v.module == "requests" for v in violations)


@pytest.mark.unit
def test_dunder_import_call_is_flagged_p17() -> None:
    """P17: ``__import__('requests')`` is also detected."""
    import textwrap

    source = textwrap.dedent(
        """
        __import__("urllib")
        """
    )
    tree = net_guard.ast.parse(source)
    violations = [
        v for node in net_guard.ast.walk(tree) for v in net_guard._check_node(node, Path("dyn.py"))
    ]
    assert any(v.module == "urllib" for v in violations)


@pytest.mark.unit
def test_relative_import_is_not_flagged_p18() -> None:
    """P18: ``from . import socket`` does NOT match the absolute forbidden
    set — relative imports resolve to local modules, not stdlib socket."""
    import textwrap

    source = textwrap.dedent(
        """
        from . import socket as _socket_local
        """
    )
    tree = net_guard.ast.parse(source)
    violations = [
        v for node in net_guard.ast.walk(tree) for v in net_guard._check_node(node, Path("rel.py"))
    ]
    assert violations == []


@pytest.mark.unit
def test_scripts_dir_is_no_longer_exempt_d7() -> None:
    """D7: ``scripts/`` removed from ``_EXEMPT_DIRS`` — supply-chain risk."""
    assert "scripts" not in net_guard._EXEMPT_DIRS
