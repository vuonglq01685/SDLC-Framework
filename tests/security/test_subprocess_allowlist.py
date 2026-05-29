"""AST gate tests for subprocess allow-list enforcement (Story 2B.6 AC2)."""

from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path

import pytest

import check_subprocess_allowlist as sp_guard
from sdlc.errors import SecurityError

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_SDLC = _REPO_ROOT / "src" / "sdlc"
_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
_FORBIDDEN_FIXTURE = _FIXTURES_DIR / "forbidden_subprocess.py"
_OS_SYSTEM_FIXTURE = _FIXTURES_DIR / "forbidden_os_system.py"
_DYNAMIC_FIXTURE = _FIXTURES_DIR / "hooks_runner_dynamic_subprocess.py"


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


# ---------------------------------------------------------------------------
# Post-review hardening (2026-05-28 bmad-code-review)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_os_system_fixture_is_flagged_p25() -> None:
    """P25 anti-tautology receipt: the AC2/D2 forbidden-list (``os.system``,
    ``os.popen``, ``os.spawn*``) is load-bearing — a fixture that calls
    ``os.system`` MUST be flagged with the correct binary and reason."""
    violations = sp_guard.scan_file(_OS_SYSTEM_FIXTURE)
    assert len(violations) >= 1
    flagged = [v for v in violations if v.binary == "os.system"]
    assert flagged, f"os.system not flagged in {violations}"
    assert "forbidden" in flagged[0].reason


@pytest.mark.unit
def test_dynamic_sentinel_allow_when_listed_p24(monkeypatch: pytest.MonkeyPatch) -> None:
    """P24 anti-tautology receipt: the AC2/D3 ``<dynamic>`` sentinel is
    load-bearing — when a fixture path is allow-listed with ``<dynamic>``,
    its truly-dynamic ``subprocess.run([var])`` call MUST produce zero
    violations.
    """
    rel = sp_guard._rel_key(_DYNAMIC_FIXTURE)
    patched_allowlist = frozenset(sp_guard._SUBPROCESS_ALLOWLIST | {(rel, sp_guard._DYNAMIC_BIN)})
    monkeypatch.setattr(sp_guard, "_SUBPROCESS_ALLOWLIST", patched_allowlist)
    violations = sp_guard.scan_file(_DYNAMIC_FIXTURE)
    assert violations == [], f"<dynamic> sentinel did not exempt: {violations}"


@pytest.mark.unit
def test_dynamic_without_sentinel_is_flagged_p12() -> None:
    """P12: with the ``len(allowed)==1`` shortcut removed, a fixture whose
    path is NOT in the allow-list MUST be flagged for its dynamic binary."""
    violations = sp_guard.scan_file(_DYNAMIC_FIXTURE)
    assert violations, "dynamic binary without <dynamic> entry should be flagged"


@pytest.mark.unit
def test_shell_true_kwarg_is_flagged_p10() -> None:
    """P10: ``shell=True`` is a violation regardless of binary."""

    src = textwrap.dedent(
        """
        import subprocess
        subprocess.run("ls", shell=True)
        """
    )
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(src)
        f.flush()
        violations = sp_guard.scan_file(Path(f.name))
    assert any(v.binary == "<shell=True>" for v in violations)


@pytest.mark.unit
def test_aliased_import_is_resolved_p9() -> None:
    """P9: ``import subprocess as sp; sp.run(...)`` resolves back to canonical."""

    src = textwrap.dedent(
        """
        import subprocess as sp
        sp.run(["arbitrary"])
        """
    )
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(src)
        f.flush()
        violations = sp_guard.scan_file(Path(f.name))
    assert any(v.binary == "arbitrary" for v in violations), violations


@pytest.mark.unit
def test_asyncio_create_subprocess_shell_is_flagged_p14() -> None:
    """P14: ``asyncio.create_subprocess_shell`` is shell-injectable; flag."""

    src = textwrap.dedent(
        """
        import asyncio
        asyncio.create_subprocess_shell("ls")
        """
    )
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(src)
        f.flush()
        violations = sp_guard.scan_file(Path(f.name))
    assert any("asyncio.create_subprocess_shell" in v.binary for v in violations), violations


@pytest.mark.unit
def test_executable_kwarg_is_inspected_p11() -> None:
    """P11: ``executable=`` kwarg overrides ``args[0]`` for binary check."""

    src = textwrap.dedent(
        """
        import subprocess
        subprocess.run(["safe"], executable="dangerous")
        """
    )
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(src)
        f.flush()
        violations = sp_guard.scan_file(Path(f.name))
    assert any(v.binary == "dangerous" for v in violations), violations


@pytest.mark.unit
def test_pty_spawn_is_flagged_p15() -> None:
    """P15: ``pty.spawn`` forks + execs."""

    src = textwrap.dedent(
        """
        import pty
        pty.spawn(["bash"])
        """
    )
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(src)
        f.flush()
        violations = sp_guard.scan_file(Path(f.name))
    assert any("pty.spawn" in v.binary for v in violations), violations


@pytest.mark.unit
def test_os_exec_family_is_flagged_p15() -> None:
    """P15: ``os.execv`` and friends."""

    src = textwrap.dedent(
        """
        import os
        os.execv("/bin/ls", ["/bin/ls"])
        """
    )
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(src)
        f.flush()
        violations = sp_guard.scan_file(Path(f.name))
    assert any(v.binary == "os.execv" for v in violations), violations
