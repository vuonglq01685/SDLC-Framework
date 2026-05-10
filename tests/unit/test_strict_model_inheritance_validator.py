"""Unit tests for scripts/check_strict_model_inheritance.py (ADR-025, D2).

Mirrors tests/unit/test_runtime_import_via_abc_validator.py pattern.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "check_strict_model_inheritance.py"
_REPO_ROOT = Path(__file__).parent.parent.parent
_CONTRACTS_DIR = _REPO_ROOT / "src" / "sdlc" / "contracts"


def _load_module() -> object:
    spec = importlib.util.spec_from_file_location("check_strict_model_inheritance", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load_module()
_check_file = _mod._check_file  # type: ignore[attr-defined]


def _write(tmp_path: Path, code: str) -> Path:
    f = tmp_path / "test_contract.py"
    f.write_text(code, encoding="utf-8")
    return f


@pytest.mark.unit
class TestStrictModelInheritanceValidator:
    def test_clean_on_strict_model_subclass(self, tmp_path: Path) -> None:
        code = (
            "from sdlc.contracts._strict_model import StrictModel\n"
            "class MyContract(StrictModel): pass\n"
        )
        assert _check_file(_write(tmp_path, code)) == []

    def test_violation_on_direct_base_model(self, tmp_path: Path) -> None:
        code = "from pydantic import BaseModel\nclass BadContract(BaseModel): pass\n"
        violations = _check_file(_write(tmp_path, code))
        assert len(violations) == 1
        lineno, msg = violations[0]
        assert lineno == 2
        assert "BadContract" in msg
        assert "StrictModel" in msg

    def test_violation_on_qualified_base_model(self, tmp_path: Path) -> None:
        code = "import pydantic\nclass BadContract(pydantic.BaseModel): pass\n"
        violations = _check_file(_write(tmp_path, code))
        assert len(violations) == 1
        assert "BadContract" in violations[0][1]

    def test_opt_out_comment_suppresses_violation(self, tmp_path: Path) -> None:
        code = (
            "from pydantic import BaseModel\n"
            "class OkBase(BaseModel):  # strict-opt-out: intentional base\n"
            "    pass\n"
        )
        assert _check_file(_write(tmp_path, code)) == []

    def test_multiple_violations_reported(self, tmp_path: Path) -> None:
        code = (
            "from pydantic import BaseModel\nclass A(BaseModel): pass\nclass B(BaseModel): pass\n"
        )
        violations = _check_file(_write(tmp_path, code))
        assert len(violations) == 2

    def test_non_basemodel_base_allowed(self, tmp_path: Path) -> None:
        code = "class MyClass(dict): pass\n"
        assert _check_file(_write(tmp_path, code)) == []

    def test_no_bases_allowed(self, tmp_path: Path) -> None:
        code = "class MyClass: pass\n"
        assert _check_file(_write(tmp_path, code)) == []


@pytest.mark.unit
class TestStrictModelProductionContracts:
    """Live gate: all current wire-format contracts must pass the linter."""

    def test_contracts_dir_is_clean(self) -> None:
        # Use the script's main scan logic on the real contracts dir.
        targets = sorted(_CONTRACTS_DIR.rglob("*.py"))
        assert targets, "no .py files found in contracts dir"
        all_violations: list[tuple[Path, int, str]] = []
        for path in targets:
            for lineno, msg in _check_file(path):
                all_violations.append((path, lineno, msg))

        assert all_violations == [], (
            "Direct BaseModel subclasses without opt-out found in contracts/:\n"
            + "\n".join(f"  {p}:{ln}: {m}" for p, ln, m in all_violations)
        )

    def test_strict_model_itself_has_opt_out(self) -> None:
        """StrictModel._strict_model.py must carry the opt-out comment."""
        strict_model_file = _CONTRACTS_DIR / "_strict_model.py"
        assert strict_model_file.exists()
        violations = _check_file(strict_model_file)
        assert violations == [], "StrictModel base class lost its opt-out comment — restore it"
